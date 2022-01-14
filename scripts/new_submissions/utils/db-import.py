#!/usr/bin/env python3
import json
import re
from getpass import getpass
from pathlib import Path

import click
from kks.ejudge import ejudge_submissions_judge, ejudge_users_judge
from kks.util.common import prompt_choice
from kks.util.ejudge import EjudgeSession

from db import BotDB, import_ej_users

try:
    from telethon.sync import TelegramClient
    telethon_available = True
except ImportError:
    telethon_available = False


def create_db(db_path, user_file, msg_file):
    """Create DB from old messages.

    Two files are needed:
    - `users.json`. Stores a dict of { abbrev_name: [id, first_name, last_name] }.
    - `msgcat.txt`. Contains concatenated messages (joined with newlines).
    """

    db = BotDB(db_path)
    db.init()

    with open(user_file) as f:
        users = json.load(f)

    for uid, first_name, last_name in users.values():
        db.add_user(uid, first_name, last_name)
    db.commit()

    with open(msg_file) as f:
        lines = f.read().split('\n')

    for line in lines:
        m = re.search(r'\[.+?\] (\d+) - .*(?: \[(.+?)\])?', line)
        if not m:
            continue
        sub_id, user = m.groups()
        if user in users:
            db.assign_submission(sub_id, users[user][0])
        else:
            db._conn.execute('INSERT OR IGNORE INTO submissions(id) VALUES (?)', (sub_id))
    db.commit()
    print(f'Imported messages into {db_path.resolve()}')


def create_dump(user_file, msg_file):
    # NOTE this script may or may not work with group chats. It was tested only with channels
    api_id = int(input('api_id (create at https://my.telegram.org/apps): '))
    api_hash = getpass('api_hash: ')
    with TelegramClient(None, api_id, api_hash) as client:
        channel_id = int(input('Channel id: '))
        users = {}
        for user in client.get_participants(channel_id):
            if not user.bot:
                first_name = user.first_name.lstrip() or ' '
                last_name = (user.last_name or '').lstrip() or ' '
                abbrev_name = first_name[0] + last_name[0]
                users[abbrev_name] = (user.id, user.first_name, user.last_name)
        msgs = []
        for msg in client.get_messages(channel_id, limit=None, reverse=True):
            if msg.message is not None:
                msgs.append(msg.message)
        client.log_out()

    with open(user_file, 'w') as f:
        json.dump(users, f)
    with open(msg_file, 'w') as f:
        f.write('\n'.join(msgs))


def v1_to_v2():
    cwd = Path.cwd().resolve()
    db_path = cwd/'caos.db'

    user_file = cwd/'users.json'
    msg_file = cwd/'msgcat.txt'

    if not (user_file.exists() and msg_file.exists()):
        if telethon_available:
            print('Using telethon to create a dump')
            create_dump(user_file, msg_file)
        else:
            print('users.json or msgcat.txt is not found')
            return
    create_db(db_path, user_file, msg_file)


def v2_to_v2_1():
    cwd = Path.cwd().resolve()
    db_path = cwd/'caos.db'
    db = BotDB(db_path)
    db.init()
    print('Importing ejudge users...', end='', flush=True)
    session = EjudgeSession()
    users = ejudge_users_judge(session, show_not_ok=True, show_invisible=True, show_banned=True)
    import_ej_users(db, users)
    print('OK')
    user_map = {u.name: u.id for u in users}
    print('Adding missing values to submissions...', end='', flush=True)
    sub_ids = [x[0] for x in db._conn.execute('SELECT id FROM submissions').fetchall()]
    if not sub_ids:
        print('No submissions found')
        return
    sub_data = []
    # Filter is passed in the query string.
    # URLs longer than 2K may not be supported.
    # ~10 chars for one id -> filter size ~= 1K.
    BATCH_SIZE = 100
    for i in range(0, len(sub_ids), BATCH_SIZE):
        filter_ = '||'.join(f'id=={sub_id}' for sub_id in sub_ids[i:i+BATCH_SIZE])
        sub_data += [
            (user_map.get(sub.user), sub.problem, sub.id)
            for sub in ejudge_submissions_judge(session, filter_, last_run=0)
        ]
    import pickle
    with open('dump', 'wb') as f:
        pickle.dump(sub_data, f)
    db._conn.executemany('UPDATE submissions SET (user, problem) = (?, ?) WHERE id = ?', sub_data)
    db.commit()
    print('OK')


def main():
    choices = [
        'Import old messages (from bot V1)',
        'Add user and problem info for old submissions (from bot V2.0)',
        click.style('Cancel', fg='red')
    ]
    choice = prompt_choice('Select action', choices)
    if choice == len(choices) - 1:
        print('Cancelled')
        return
    if choice == 0:
        return v1_to_v2()
    elif choice == 1:
        return v2_to_v2_1()


if __name__ == '__main__':
    main()
