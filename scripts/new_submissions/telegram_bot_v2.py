#!/usr/bin/env python3

import re
import logging
import typing as t
from os import environ
from pathlib import Path
from random import randint
from time import sleep
from traceback import format_exc

import click
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.error import RetryAfter, TelegramError
from telegram.ext import CallbackContext, CallbackQueryHandler, Updater
from telegram.utils.helpers import escape_markdown

from kks.ejudge import Status, Submission
from utils.submissions import new_submissions, save_last_id
from utils.db import BotDB


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.WARNING
)
logger = logging.getLogger(__name__)


STRIKETHROUGH = '~'
# TODO use config
TOKEN = environ.get('EJUDGE_TELEGRAM_TOKEN')
CHAT_ID = environ.get('EJUDGE_TELEGRAM_CHAT')
# compatibility
BASE_DIR = Path(__file__).resolve().parent
ID_FILE = BASE_DIR/'last_run_id'


def handle_query(update: Update, context: CallbackContext):
    # race conditions?
    choice_index = int(context.match.group(1))
    query = update.callback_query
    message = query.message
    user = query.from_user
    first_name = user.first_name.lstrip() or ' '
    last_name = (user.last_name or '').lstrip() or ' '
    lines = message.text_markdown_v2.split('\n')
    lines[choice_index] = (
        STRIKETHROUGH + lines[choice_index] + STRIKETHROUGH +
        escape_markdown(f' [{first_name[0]}{last_name[0]}]', version=2)
    )
    keyboard = message.reply_markup.inline_keyboard
    keyboard = [row for row in keyboard if row[0].callback_data != query.data]
    try:
        message.edit_text('\n'.join(lines), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='MarkdownV2')
    except RetryAfter as err:
        update.callback_query.answer(f'Rate limit, retry in {round(err.retry_after)}s')
    except TelegramError:
        logger.error('Message update error:')
        logger.error(format_exc())
        update.callback_query.answer('Unknown error, retry later')
    else:
        update.callback_query.answer()


def send_message(context: CallbackContext, text, keyboard=None, retries=3):
    for i in range(retries):
        try:
            context.bot.send_message(chat_id=CHAT_ID, text=text, reply_markup=keyboard)
            return
        except RetryAfter as err:
            if i < retries - 1:
                sleep(err.retry_after)
            else:
                logger.error('Cannot send message: max retries exceeded')
                raise


def send_messages(
    context: CallbackContext,
    messages: t.List[t.Tuple[str, t.Optional[InlineKeyboardMarkup]]],
    retries=3
):
    delay = 1
    if len(messages) >= 20:
        # Rate limit for groups and channels is 20 messages / 60s.
        # A higher delay is used to reduce the chance of hitting the rate limit.
        delay = 4
    for (text, keyboard) in messages:
        send_message(context, text, keyboard, retries)
        sleep(delay)  # use MessageQueue?


def post_pending(context: CallbackContext, pending: t.List[Submission]):
    batch_size = 10
    messages = []
    for i in range(0, len(pending), batch_size):
        lines = []
        buttons = []
        for sub in pending[i:i+batch_size]:
            lines.append(
                f'[{sub.time.strftime("%d.%m %H:%M:%S")}] {sub.id} - {sub.user} - {sub.problem} ({sub.score})'
            )
            buttons.append(InlineKeyboardButton(f'Take run {sub.id}', callback_data=f'{len(lines) - 1}_{randint(1, 10**9)}'))
        messages.append(('\n'.join(lines), InlineKeyboardMarkup.from_column(buttons)))
    send_messages(context, messages)


def check_updates(context: CallbackContext):
    try:
        submissions = new_submissions(ID_FILE)
    except Exception:
        logger.error('Cannot get new submissions. Error:')
        logger.error(format_exc())
        return
    if not submissions:
        logger.info('No new submissions')
        return

    pending = []
    for sub in submissions:
        if sub.status == Status.REVIEW:
            pending.append(sub)
    pending.sort(key=lambda sub: sub.problem)

    try:
        if pending:
            post_pending(context, pending)
    except TelegramError:
        logger.error('Cannot post an update. Error:')
        logger.error(format_exc())
        return

    # Update last id only if all updates were successfully posted.
    save_last_id(submissions, ID_FILE)


def main() -> None:
    if TOKEN is None:
        click.secho('Telegram token is not set', err=True, fg='red')
        return
    if CHAT_ID is None:
        click.secho('Chat id is not set', err=True, fg='red')
        return

    updater = Updater(TOKEN)
    updater.dispatcher.add_handler(CallbackQueryHandler(
        handle_query,
        pattern=re.compile(r'^(\d+)_.+$')
    ))
    updater.job_queue.run_custom(check_updates, {'trigger': 'cron', 'minute': 0})

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
