#!/usr/bin/env python3
import sqlite3
from functools import wraps
from threading import Lock


def db_method(method):

    @wraps(method)
    def wrapper(*args, **kwargs):
        self = args[0]
        with self._lock:
            result = method(*args, **kwargs)
            if kwargs.get('commit'):
                self._commit()
        return result

    return wrapper


class BotDB:
    def __init__(self, path):
        self._lock = Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)

    def __del__(self):
        self._conn.close()

    @db_method
    def create_tables(self, *, commit=True):
        if self._conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'").fetchone() is not None:
            return
        self._conn.execute('CREATE TABLE IF NOT EXISTS users (id int, first_name str, last_name str, PRIMARY KEY (id));')
        self._conn.execute('CREATE TABLE IF NOT EXISTS submissions (id int, reviewer int, PRIMARY KEY (id), FOREIGN KEY (reviewer) REFERENCES users(id));')
        self._conn.execute('CREATE INDEX IF NOT EXISTS idx_reviewer ON submissions(reviewer);')

    @db_method
    def user_exists(self, uid):
        return self._conn.execute('SELECT id FROM users WHERE id = ?', (uid,)).fetchone() is not None

    @db_method
    def get_user(self, uid):
        return self._conn.execute('SELECT * FROM users WHERE id = ?', (uid,)).fetchone()

    @db_method
    def add_user(self, uid, first_name, last_name, *, commit=False):
        self._conn.execute('INSERT OR IGNORE INTO users(id, first_name, last_name) VALUES (?, ?, ?)', (uid, first_name, last_name))

    @db_method
    def get_submission(self, sub_id):
        return self._conn.execute('SELECT * FROM submissions WHERE id = ?', (sub_id,)).fetchone()

    @db_method
    def add_submission(self, sub_id, uid, *, commit=False):
        self._conn.execute('INSERT OR IGNORE INTO submissions(id, reviewer) VALUES (?, ?)', (sub_id, uid))

    def commit(self):
        with self._lock:
            self._commit()

    def _commit(self):
        self._conn.commit()
