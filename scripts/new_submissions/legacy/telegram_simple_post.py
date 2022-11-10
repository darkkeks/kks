#!/usr/bin/env python3
from collections import Counter
from os import environ
from pathlib import Path

import requests
import click

from kks.ejudge import Status
from submissions import new_submissions, save_last_id


# compatibility
BASE_DIR = Path(__file__).resolve().parent
ID_FILE = BASE_DIR/'last_run_id'


def send_message(token, chat_id, lines):
    """Splits long text into multiple messages"""
    def _send(text):
        if not text:
            return
        requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            data={'chat_id': chat_id, 'text': text}
        ).raise_for_status()

    buf = []
    total_length = 0
    for line in lines:
        line_length = len(line)
        if buf:  # count newline
            line_length += 1
        if total_length + line_length > 4096:
            _send('\n'.join(buf))
            buf = []
            total_length = 0
            line_length -= 1  # no newline
        buf.append(line)
        total_length += line_length
    if buf:
        _send('\n'.join(buf))
    text = '\n'.join(lines)


def main():
    token = environ.get('EJUDGE_TELEGRAM_TOKEN')
    chat_id = environ.get('EJUDGE_TELEGRAM_CHAT')
    if token is None:
        click.secho('Telegram token is not set', err=True, fg='red')
        return
    if chat_id is None:
        click.secho('Chat id is not set', err=True, fg='red')
        return

    submissions = new_submissions(ID_FILE)
    if not submissions:
        return

    pending = []
    counts = Counter()
    for sub in submissions:
        if sub.status == Status.REVIEW:
            pending.append(sub)
        else:
            counts[sub.status] += 1
    lines = []
    if pending:
        lines.append('Pending:')
        lines += [
            f'[{sub.time.strftime("%d.%m %H:%M:%S")}] {sub.id} - {sub.user} - {sub.problem} ({sub.score})'
            for sub in pending
        ]
    if counts:
        if pending:
            lines.append('')
            lines.append('Other submissions:')
        else:
            lines.append('New submissions:')
        lines += [
            f'{status}: {cnt}' for status, cnt in sorted(counts.items())
        ]

    # If an exception is raised, just silently fail. In this case last id won't be updated
    send_message(token, chat_id, lines)
    save_last_id(submissions, ID_FILE)


if __name__ == '__main__':
    main()
