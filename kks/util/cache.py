import gzip
import pickle
from datetime import datetime, timedelta
from time import time

import click

from kks.util.common import config_directory

class Cache:
    def __init__(self, name, compress=False):

        self.name = name
        self.compress = compress

        suffix = '.pickle.gz' if compress else '.pickle'
        self._file = (config_directory() / name).with_suffix(suffix)
        self._data = {}
        self._clean = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.save()

    def load(self):
        self._clean = True
        if self._file.exists():
            with self._file.open('rb') as f:
                try:
                    data = f.read()
                    if self.compress:
                        data = gzip.decompress(data)
                    self._data = pickle.loads(data)
                except Exception:
                    self._data = {}
                    click.secho(f'Cache file {self._file} is corrupted, erasing all cached data', bg='red', err=True)
                    self._clean = False
        else:
            self._data = {}
        return self

    def keys(self):
        return self._data.keys()

    def get(self, key, default=None):
        # default is returned if value is not found or outdated
        value, exp_time = self._data.get(key, (None, -1))
        if exp_time == -1:
            return default
        if exp_time is not None and time() > exp_time:
            del self._data[key]
            self._clean = False
            return default
        return value

    def set(self, key, value, expiration=None):
        """
        expiration may be None, datetime or timedelta
        If expiration is None, value is never outdated
        """
        if expiration is None:
            exp_time = None
        elif isinstance(expiration, datetime):
            exp_time = int(expiration.timestamp())
        elif isinstance(expiration, timedelta):
            exp_time = int(time() + expiration.total_seconds())
        else:
            raise TypeError('Invalid argument type')

        self._data[key] = (value, exp_time)
        self._clean = False

    def erase(self, key):
        # If key is not found, no errors are raised
        value, exp_time = self._data.pop(key, (None, -1))
        if exp_time != -1:
            self._clean = False

    def clear(self):
        if self._data:
            self._data = {}
            self._clean = False

    def save(self):
        if self._clean:
            return
        with self._file.open('wb') as f:
            data = pickle.dumps(self._data)
            if self.compress:
                data = gzip.compress(data)
            f.write(data)
