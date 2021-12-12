#!/usr/bin/env python3
import json
import re
from getpass import getpass
from pathlib import Path
from db import BotDB

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
    db.create_tables()

    with open(user_file) as f:
        users = json.load(f)

    for uid, first_name, last_name in users.values():
        db.add_user(uid, first_name, last_name)
    db.commit()

    with open(msg_file) as f:
        lines = f.read().split('\n')

    for line in lines:
        m = re.search(r'\[.+?\] (\d+) - .* \[(.+?)\]', line)
        if not m:
            continue
        sub_id, user = m.groups()
        if user not in users:
            continue
        db.add_submission(sub_id, users[user][0])
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


def main():
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


if __name__ == '__main__':
    main()
