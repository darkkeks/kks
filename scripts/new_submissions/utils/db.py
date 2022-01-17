#!/usr/bin/env python3
import sqlite3
from functools import wraps
from threading import RLock


__version__ = '0.2.0'


class UnknownUser(Exception):
    pass


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


def import_ej_users(db, users):
    with db.lock:
        for user in users:
            db.add_ej_user(user.id, user.name or user.login)
        db.commit()


class BotDB:
    def __init__(self, path):
        self._lock = RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute('PRAGMA foreign_keys = ON')

    def __del__(self):
        self._conn.close()

    @db_method
    def init(self, *, commit=True):
        self._create_tables()
        self._add_columns()
        self._create_indices()

    def _create_tables(self):
        if self._conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ej_users'").fetchone() is not None:
            return
        self._conn.execute(
            'CREATE TABLE IF NOT EXISTS users ('
            'id int, first_name str, last_name str, PRIMARY KEY (id)'
            ')'
        )
        self._conn.execute(
            'CREATE TABLE IF NOT EXISTS ej_users (id int, name str, PRIMARY KEY (id))'
        )
        self._conn.execute(
            'CREATE TABLE IF NOT EXISTS submissions ('
            'id int, reviewer int, user int, problem str, '
            'PRIMARY KEY (id), '
            'FOREIGN KEY (reviewer) REFERENCES users(id), '
            'FOREIGN KEY (user) REFERENCES ej_users(id)'
            ')'
        )

    def _add_columns(self):
        # return if the last column already exists?
        for query in [
            'ALTER TABLE submissions ADD COLUMN user int;',
            'ALTER TABLE submissions ADD COLUMN problem str;'
        ]:
            try:
                self._conn.execute(query)
            except sqlite3.OperationalError as e:
                if not str(e).startswith('duplicate column name'):
                    raise

    def _create_indices(self):
        # return if the last index already exists?
        self._conn.execute('CREATE INDEX IF NOT EXISTS idx_ej_user_name ON ej_users(name)')
        self._conn.execute('CREATE INDEX IF NOT EXISTS idx_reviewer ON submissions(reviewer)')
        self._conn.execute('CREATE INDEX IF NOT EXISTS idx_user_prob ON submissions(user, problem)')

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
    def has_ej_users(self):
        return bool(self._conn.execute('SELECT count(*) FROM ej_users').fetchone()[0])

    @db_method
    def add_ej_user(self, uid, name, *, commit=False):
        self._conn.execute('INSERT OR IGNORE INTO ej_users(id, name) VALUES (?, ?)', (uid, name))

    @db_method
    def find_ej_user(self, name):
        return self._conn.execute('SELECT * FROM ej_users WHERE name = ?', (name,)).fetchone()

    @db_method
    def get_submission(self, sub_id):
        return self._conn.execute('SELECT * FROM submissions WHERE id = ?', (sub_id,)).fetchone()

    @db_method
    def add_submission(self, sub, *, commit=False):
        user = self.find_ej_user(sub.user)
        user_id = user[0] if user else None
        self._conn.execute('INSERT OR IGNORE INTO submissions(id, user, problem) VALUES (?, ?, ?)', (sub.id, user_id, sub.problem))

    @db_method
    def assign_submission(self, sub_id, reviewer_id, *, commit=False):
        # If there was no add_submission calls
        self._conn.execute('INSERT OR IGNORE INTO submissions(id, reviewer) VALUES (?, ?)', (sub_id, reviewer_id))
        # Assign at most once
        self._conn.execute('UPDATE submissions SET reviewer = ? WHERE id = ? AND reviewer IS NULL', (reviewer_id, sub_id))

    @db_method
    def get_previous_reviewer(self, sub):
        user = self.find_ej_user(sub.user)
        if user is None:  # new user?
            raise UnknownUser()
        user_id = user[0]
        row = self._conn.execute('SELECT reviewer FROM submissions WHERE (user, problem) = (?, ?) AND id < ? ORDER BY id DESC LIMIT 1', (user_id, sub.problem, sub.id)).fetchone()
        if row is not None:
            return self.get_user(row[0])
        return None

    @db_method
    def get_stats(self):
        return self._conn.execute('SELECT reviewer, COUNT(id) FROM submissions WHERE reviewer IS NOT NULL GROUP BY reviewer').fetchall()

    @db_method
    def dump_submissions(self):
        header = ('id', 'ej_user', 'problem', 'first_name', 'last_name', 'tg_user_id')
        data = self._conn.execute(
            'SELECT s.id, eu.name, s.problem, u.first_name, u.last_name, u.id '
            'FROM submissions AS s '
            'INNER JOIN users AS u ON (s.reviewer = u.id) '
            'LEFT JOIN ej_users AS eu ON (s.user = eu.id) ').fetchall()
        return header, data

    @property
    def lock(self):
        return self._lock

    def commit(self):
        with self._lock:
            self._commit()

    def _commit(self):
        self._conn.commit()
