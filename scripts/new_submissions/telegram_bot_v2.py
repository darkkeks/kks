#!/usr/bin/env python3

import argparse
import re
import logging
import typing as t
from pathlib import Path
from random import randint
from time import sleep
from traceback import format_exc

import yaml
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.error import BadRequest, RetryAfter, TelegramError
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


class Bot:
    def __init__(self, token, chat_id, id_file, db_path):
        self.updater = Updater(token)
        self.chat_id = chat_id
        self.id_file = id_file
        self.db = BotDB(db_path)

        self.updater.dispatcher.add_handler(CallbackQueryHandler(
            self.handle_query,
            pattern=re.compile(r'^(\d+)_\d+(?:_(\d+))?$')
        ))

    def start(self):
        self.db.create_tables()
        self.updater.job_queue.run_custom(self.check_updates, {'trigger': 'cron', 'minute': 0})
        self.updater.start_polling()
        self.updater.idle()

    def handle_query(self, update: Update, context: CallbackContext):
        if update.effective_chat is None or update.effective_chat.id != self.chat_id:
            return

        # Handler is synchronous => no need for additional locks
        idx, sub_id = context.match.groups()
        choice_index = int(idx)
        query = update.callback_query
        message = query.message
        user = query.from_user
        if not self.db.user_exists(user.id):
            self.db.add_user(user.id, user.first_name, user.last_name, commit=True)
        lines = message.text_markdown_v2.split('\n')

        if sub_id is not None:
            sub_id = int(sub_id)
        else:
            # Text is escaped markdown, so we need more backslashes.
            match = re.match(r'\\\[[^\]]+\\\] (\d+)', lines[choice_index])
            if match is not None:
                sub_id = int(match.group(1))

        old_uid = None
        if sub_id is not None:
            sub = self.db.get_submission(sub_id)
            if sub is not None:
                # NOTE A version conflict is possible.
                # Case 1:
                # A message contains runs 1 and 2.
                # The bot receives 2 queries, they are processed synchronously:
                # - User A: remove run 1 from (1, 2). Response: (2); run 1 is stored in db.
                # - User B: remove run 2 from (1, 2). Response: (1); run 2 is stored in db.
                # The final message contains run 1, which was previously removed.
                # In this case, the user will likely retry the request. Then versions will be merged.
                # Case 2:
                # Two users take the same run. The second query should be ignored.
                old_uid = sub[1]

        keyboard = message.reply_markup.inline_keyboard
        keyboard = [row for row in keyboard if row[0].callback_data != query.data]
        not_empty = len(keyboard) > 0
        if not_empty:
            # Edit the message and keyboard
            if old_uid is not None and old_uid != user.id:
                # Version conflict, see note above. Try to merge versions.
                # Case 1: remove run 1 from 2nd version. All should be OK.
                # Case 2: reapply the first request. BadRequest will be raised (see below), but it's OK.
                _, first_name, last_name = self.db.get_user(old_uid)
            else:
                first_name = user.first_name
                last_name = user.last_name
            first_name = first_name.lstrip() or ' '
            last_name = (last_name or '').lstrip() or ' '
            lines[choice_index] = (
                STRIKETHROUGH + lines[choice_index] + STRIKETHROUGH +
                escape_markdown(f' [{first_name[0]}{last_name[0]}]', version=2)
            )

        try:  # any better options to filter BadRequest's?
            try:
                if not_empty:
                    message.edit_text(
                        '\n'.join(lines),
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='MarkdownV2'
                    )
                else:
                    if old_uid is not None and old_uid != user.id:
                        update.callback_query.answer('This run is taken by another user')
                    message.delete()
            except BadRequest as e:
                if str(e).startswith('Message is not modified') or str(e).startswith('Message to delete not found'):
                    # Case 2 from above
                    pass
                else:
                    raise
        except RetryAfter as err:
            update.callback_query.answer(f'Rate limit, retry in {round(err.retry_after)}s')
            return
        except TelegramError:
            logger.error('Message update error:')
            logger.error(format_exc())
            update.callback_query.answer('Unknown error, retry later')
            return

        # NOTE If the bot is stopped at this point, the run can be lost. Is it possible to make updates atomic?
        self.db.add_submission(sub_id, user.id, commit=True)

        if old_uid is None or old_uid == user.id:
            update.callback_query.answer()
            return
        update.callback_query.answer('This run is taken by another user')

    def check_updates(self, context: CallbackContext):
        try:
            submissions = new_submissions(self.id_file)
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
                self.post_pending(context, pending)
        except TelegramError:
            logger.error('Cannot post an update. Error:')
            logger.error(format_exc())
            return

        # Update last id only if all updates were successfully posted.
        save_last_id(submissions, self.id_file)

    def post_pending(self, context: CallbackContext, pending: t.List[Submission]):
        batch_size = 10
        messages = []
        for i in range(0, len(pending), batch_size):
            lines = []
            buttons = []
            for sub in pending[i:i+batch_size]:
                lines.append(
                    f'[{sub.time.strftime("%d.%m %H:%M:%S")}] {sub.id} - {sub.user} - {sub.problem} ({sub.score})'
                )
                buttons.append(InlineKeyboardButton(
                    f'Take run {sub.id}',
                    callback_data=f'{len(lines) - 1}_{randint(1, 10**9)}_{sub.id}'
                ))
            messages.append(('\n'.join(lines), InlineKeyboardMarkup.from_column(buttons)))
        self._send_messages(context, self.chat_id, messages)

    def _send_message(self, context: CallbackContext, chat_id, text, keyboard=None, retries=3):
        for i in range(retries):
            try:
                context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
                return
            except RetryAfter as err:
                if i < retries - 1:
                    sleep(err.retry_after)
                else:
                    logger.error('Cannot send message: max retries exceeded')
                    raise

    def _send_messages(
        self,
        context: CallbackContext,
        chat_id,
        messages: t.List[t.Tuple[str, t.Optional[InlineKeyboardMarkup]]],
        retries=3
    ):
        delay = 1
        if len(messages) >= 20:
            # Rate limit for groups and channels is 20 messages / 60s.
            # A higher delay is used to reduce the chance of hitting the rate limit.
            delay = 4
        for (text, keyboard) in messages:
            self._send_message(context, chat_id, text, keyboard, retries)
        sleep(delay)  # NOTE check MessageQueue from PTB


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', metavar='FILE', type=Path, required=True,
                        help='Config file')
    args = parser.parse_args()
    config_file = args.config.resolve()

    if not config_file.is_file():
        logger.error(f'{config_file} is not a file')
        return

    with config_file.open('r') as f:
        try:
            config = yaml.safe_load(f)
        except yaml.parser.ParserError:
            logger.error(f'Cannot parse {config_file}')
            return

    try:
        token = config['token']
        chat_id = config['chat_id']
        id_file = config['id_file']
        db_path = config['db_path']
    except KeyError as e:
        logger.error(f'Missing config key: "{e.args[0]}"')
        return

    def get_path(path_str):
        path = Path(path_str)
        if path.is_absolute():
            return path
        return config_file.parent/path

    id_file = get_path(id_file)
    db_path = get_path(db_path)

    bot = Bot(token, chat_id, id_file, db_path)
    bot.start()


if __name__ == '__main__':
    main()
