#!/usr/bin/env python3

import argparse
import csv
import re
import logging
import typing as t

from dataclasses import dataclass
from functools import wraps
from io import StringIO
from pathlib import Path
from random import randint
from time import sleep
from traceback import format_exc

import yaml

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.error import BadRequest, RetryAfter, TelegramError
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler, Filters, Updater
from telegram.utils.helpers import escape_markdown

from kks.ejudge_priv import Submission, ejudge_submissions, ejudge_users
from kks.util.ejudge import AuthData, EjudgeSession, RunField, RunStatus
from utils.submissions import new_submissions
from utils.db import BotDB


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.WARNING
)
logger = logging.getLogger(__name__)


# Unused
__version__ = '3.0.0'


DEFAULT_DB_FILE =  Path('/data/caos.db')


STRIKETHROUGH = '~'
BOLD = '*'


class AllowDuplicateRequests:
    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, traceback):
        if not isinstance(exc_value, BadRequest):
            return False
        err_msg = str(exc_value)
        if err_msg.startswith('Message is not modified') or err_msg.startswith('Message to delete not found'):
            # Ignore these errors. See Case 2 in note about version conflicts below.
            return True
        return False


def restricted_cmd(method):

    @wraps(method)
    def wrapper(*args, **kwargs):
        self, update = args[:2]
        uid = update.effective_user.id
        if not self.db.user_exists(uid):
            logger.warning(f'Unauthorized command from user {uid}')
            return
        return method(*args, **kwargs)

    return wrapper


def abbrev_name(first_name, last_name):
    first_name = first_name.lstrip() or ' '
    last_name = (last_name or '').lstrip() or ' '
    return first_name[0] + last_name[0]


@dataclass
class TelegramConfig:
    token: str
    chat_id: int


@dataclass
class EjudgeConfig:
    contest: int
    login: str
    password: str


class Bot:
    def __init__(self, tg_conf: TelegramConfig, ej_conf: EjudgeConfig, db_path: str):
        self.updater = Updater(tg_conf.token)
        self.chat_id = tg_conf.chat_id
        self.db = BotDB(db_path)
        self._field_mask = (
            RunField.ID |
            RunField.TIME |
            RunField.USER_ID |
            RunField.USER |
            RunField.PROB_NAME |
            RunField.LANG_NAME |
            RunField.STATUS |
            RunField.SCORE
        )
        # TODO add session lock?
        self.session = EjudgeSession(auth_data=AuthData(ej_conf.login, ej_conf.password, ej_conf.contest, judge=True), quiet=True)

        self.updater.dispatcher.add_handler(CallbackQueryHandler(
            self.handle_query,
            pattern=re.compile(r'^(\d+)_\d+_(\d+)$')
        ))
        self.updater.dispatcher.add_handler(CommandHandler('get', self.get_reviewer, Filters.chat_type.private))
        self.updater.dispatcher.add_handler(CommandHandler('take', self.take_run, Filters.chat_type.private))
        self.updater.dispatcher.add_handler(CommandHandler('stats', self.show_stats, Filters.chat_type.private))
        self.updater.dispatcher.add_handler(CommandHandler('dump', self.create_dump, Filters.chat_type.private))

    def start(self):
        logger.info('Starting')
        logger.info('Initializing the database')
        self.db.init()
        if not self.db.has_ej_users():
            logger.info('Adding ejudge users')
            # Add invisible/banned/not-ok users to avoid unnecessary updates on submissions from these users.
            users = ejudge_users(self.session, show_not_ok=True, show_invisible=True, show_banned=True)
            with self.db.lock:
                for user in users:
                    self.db.add_ej_user(user.id, user.name or user.login)
                self.db.commit()
        logger.info('Creating a cron job')
        self.updater.job_queue.run_custom(self.check_updates, {'trigger': 'cron', 'minute': 0})
        logger.info('Start polling')
        self.updater.start_polling()
        logger.info('Started')
        self.updater.idle()

    def handle_query(self, update: Update, context: CallbackContext):
        if update.effective_chat is None or update.effective_chat.id != self.chat_id:
            return

        # Handler is synchronous => no need for additional locks
        choice_index, sub_id = map(int, context.match.groups())
        query = update.callback_query
        message = query.message
        user = query.from_user
        if not self.db.user_exists(user.id):
            self.db.add_user(user.id, user.first_name, user.last_name, commit=True)
        lines = message.text_markdown_v2.split('\n')
        line = lines[choice_index]

        old_uid = None
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
                # Case 2: reapply the first request. BadRequest will be raised, but it's OK.
                _, first_name, last_name = self.db.get_user(old_uid)
            else:
                first_name = user.first_name
                last_name = user.last_name
            line = re.sub(r' \\\[Prev: ..\\\]$', '', line)
            lines[choice_index] = (
                STRIKETHROUGH + line + STRIKETHROUGH +
                escape_markdown(f' [{abbrev_name(first_name, last_name)}]', version=2)
            )

        try:  # Generic telegram error handling
            try:  # Filter BadRequest's. If we can't delete an old message, just edit it.
                with AllowDuplicateRequests():
                    if old_uid is not None and old_uid != user.id:
                        # Need to answer the query while the message still exists
                        update.callback_query.answer('This run is taken by another user')
                    if not_empty:
                        message.edit_text(
                            '\n'.join(lines),
                            reply_markup=InlineKeyboardMarkup(keyboard),
                            parse_mode='MarkdownV2'
                        )
                    else:
                        message.delete()
            except BadRequest as e:
                if str(e).startswith('Message can\'t be deleted'):
                    # TODO check this error. From bot API docs:
                    # > A message can only be deleted if it was sent less than 48 hours ago.
                    # > If the bot has can_delete_messages permission in a supergroup or a channel,
                    #   it can delete any message there.
                    with AllowDuplicateRequests():
                        message.edit_text(
                            BOLD + escape_markdown('[DELETED]', version=2) + BOLD,
                            parse_mode='MarkdownV2'
                        )
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
        if sub_id is not None:
            self.db.assign_submission(sub_id, user.id, commit=True)

        if old_uid is None or old_uid == user.id:
            update.callback_query.answer()
            return
        update.callback_query.answer('This run is taken by another user')

    @restricted_cmd
    def get_reviewer(self, update: Update, context: CallbackContext):
        cid = update.effective_chat.id
        run_id = None
        if context.args:
            try:
                run_id = int(context.args[0])
            except ValueError:
                pass
        if run_id is None:
            context.bot.send_message(cid, 'Usage: /get RUN_ID')
            return
        sub = self.db.get_submission(run_id)
        if sub is None:
            context.bot.send_message(cid, 'Submission is not in database')
            return
        _, reviewer, *_ = sub
        if reviewer is None:
            context.bot.send_message(
                cid,
                f'Run {run_id} was not reviewed or was not marked as reviewed'
            )
            return
        _, first_name, last_name = self.db.get_user(reviewer)
        full_name = f'{first_name} {last_name}' if last_name else first_name
        full_name = escape_markdown(full_name, version=2)
        context.bot.send_message(
            cid,
            f'{run_id} \\- [{full_name}](tg://user?id={reviewer})',
            parse_mode='MarkdownV2'
        )

    @restricted_cmd
    def take_run(self, update: Update, context: CallbackContext):
        cid = update.effective_chat.id
        run_id = None
        if context.args:
            try:
                run_id = int(context.args[0])
            except ValueError:
                pass
        if run_id is None:
            context.bot.send_message(cid, 'Usage: /take RUN_ID')
            return
        sub = self.db.get_submission(run_id)
        if sub is not None and sub[1] is not None:
            context.bot.send_message(cid, 'Submission has already been reviewed')
            return
        res = ejudge_submissions(self.session, f'id == {run_id}', field_mask=self._field_mask)
        if not res:
            context.bot.send_message(cid, 'Submission does not exist')
            return
        sub = res[0]
        self.db.add_submission(sub)
        uid = update.effective_user.id
        self.db.assign_submission(sub.id, uid, commit=True)
        context.bot.send_message(
            cid, 'OK'
        )


    @restricted_cmd
    def show_stats(self, update: Update, context: CallbackContext):
        stats = self.db.get_stats()
        stats.sort(key=lambda x: x[1], reverse=True)
        lines = []
        for uid, runs in stats:
            _, first_name, last_name = self.db.get_user(uid)  # Use a single SELECT?
            full_name = f'{first_name} {last_name}' if last_name else first_name
            lines.append(f'{full_name}: {runs}')
        if not lines:
            lines.append('No reviewed runs :(')
        context.bot.send_message(update.effective_chat.id, '\n'.join(lines))

    @restricted_cmd
    def create_dump(self, update: Update, context: CallbackContext):
        output = StringIO()
        header, data = self.db.dump_submissions()
        csv.writer(output).writerows(
            [header] + data
        )
        output.seek(0)
        context.bot.send_document(update.effective_chat.id, output, 'submissions.csv')

    def check_updates(self, context: CallbackContext):
        # TODO check clars to add commented runs which have already been reviewed
        try:
            submissions = new_submissions(self.session, self.db.get_last_run_id(), self._field_mask)
        except Exception:
            logger.error('Cannot get new submissions. Error:')
            logger.error(format_exc())
            return
        if not submissions:
            logger.info('No new submissions')
            return

        pending = []
        for sub in submissions:
            if sub.status == RunStatus.PENDING_REVIEW:
                pending.append(sub)
        if pending:
            with self.db.lock:
                for sub in pending:
                    self.db.add_submission(sub)
                self.db.commit()
        pending.sort(key=lambda sub: sub.problem)

        try:
            if pending:
                self.post_pending(context, pending)
        except TelegramError:
            logger.error('Cannot post an update. Error:')
            logger.error(format_exc())
            return

        # Update last id only if all updates were successfully posted.
        self.db.set_last_run_id(submissions[-1].id)

    def post_pending(self, context: CallbackContext, pending: t.List[Submission]):
        batch_size = 10
        messages = []
        for i in range(0, len(pending), batch_size):
            lines = []
            buttons = []
            for sub in pending[i:i+batch_size]:
                time_str = sub.time.strftime('%d.%m %H:%M:%S')
                line = f'[{time_str}] {sub.id} - {sub.user} - {sub.problem} ({sub.score})'
                reviewer = self.db.get_previous_reviewer(sub)
                if reviewer:
                    _, first_name, last_name = reviewer
                    line += f' [Prev: {abbrev_name(first_name, last_name)}]'
                lines.append(line)
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
    parser.add_argument('config_file')
    args = parser.parse_args()
    config_file = Path(args.config_file)
    if not config_file.exists():
        logger.error(f'"{config_file}" does not exit')
        return
    if not config_file.is_file():
        logger.error(f'"{config_file}" is not a file')
        return
    try:
        with config_file.open() as f:
            config = yaml.safe_load(f)
        tg_conf = TelegramConfig(**config['telegram'])
        ej_conf = EjudgeConfig(**config['ejudge'])
        if 'db_file' in config:
            db_file = config_file.parent / config['db_file']
        else:
            db_file = DEFAULT_DB_FILE
    except KeyError as e:
        logger.error(f'Missing config key: "{e.args[0]}"')
        return
    except Exception as e:
        logger.error(f'Bad config: {e}')
        return

    bot = Bot(tg_conf, ej_conf, db_file)
    bot.start()


if __name__ == '__main__':
    main()