import gzip
import pickle
from configparser import ConfigParser
from datetime import datetime, timedelta
from time import time

import click

from kks.util.common import Singleton, config_directory


class Config(ConfigParser, metaclass=Singleton):
    """global kks config"""
    def __init__(self):
        super().__init__()
        self.optionxform = str
        self._file = config_directory() / 'config.ini'
        if self._file.is_file():
            self.read(self._file)
        # delete legacy section
        if self.has_section('Links'):
            self.remove_section('Links')

    def save(self):
        with self._file.open('w') as f:
            self.write(f)

    def reload(self):
        """force reload from disk"""
        if self._file.is_file():
            self.read(self._file)

    def has_boolean_option(self, option):
        return self.has_option('Options', option)

    def get_boolean_option(self, option, default=False):
        return self.getboolean('Options', option, fallback=default)

    def set_boolean_option(self, option, value):
        if not self.has_section('Options'):
            self.add_section('Options')
        return self.set('Options', option, 'yes' if value else 'no')


class PickleStorage:
    _service_keys = ('__version__',)

    def __init__(self, name, compress=False, version=1):

        self.name = name
        self.compress = compress

        suffix = '.pickle.gz' if compress else '.pickle'
        self._file = (config_directory() / name).with_suffix(suffix)
        self._version = version
        self._init_data()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.save()

    def _init_data(self, clean=True):
        self._data = {'__version__': self._version}
        self._clean = clean

    def load(self):
        self._init_data()

        if self._file.exists():
            try:
                with self._file.open('rb') as f:
                    data = f.read()
                if self.compress:
                    data = gzip.decompress(data)
                self._data.update(pickle.loads(data))
            except Exception:
                # anyway we cannot restore it
                click.secho(f'Storage file {self._file} is corrupted, erasing all saved data', bg='red', err=True)
                self._init_data(False)

        if self._data['__version__'] != self._version:
            click.secho(f'{self._file} uses an incompatible storage version, clearing saved data', bg='red', err=True)
            self._init_data(False)
        return self

    def keys(self):
        for k in self._data.keys():
            if k not in self._service_keys:
                yield k

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
        self._clean = False

    def erase(self, key):
        # If key is not found, no errors are raised
        if key in self._data:
            del self._data[key]
            self._clean = False

    def clear(self):
        if len(self._data) > len(self._service_keys):
            self._init_data(False)

    def save(self):
        if self._clean:
            return
        with self._file.open('wb') as f:
            data = pickle.dumps(self._data)
            if self.compress:
                data = gzip.compress(data)
            f.write(data)


class Cache(PickleStorage):
    """Storage for data with expiration times"""
    def get(self, key, default=None):
        # default is returned if value is not found or outdated
        value, exp_time = super().get(key, (None, -1))
        if exp_time == -1:
            return default
        if exp_time is not None and time() > exp_time:
            self.erase(key)
            return default
        return value

    def set(self, key, value, expiration=None):
        """
        expiration may be None, datetime or timedelta
        If expiration is None, value will never become outdated
        """
        if expiration is None:
            exp_time = None
        elif isinstance(expiration, datetime):
            exp_time = int(expiration.timestamp())
        elif isinstance(expiration, timedelta):
            exp_time = int(time() + expiration.total_seconds())
        else:
            raise TypeError('Invalid argument type')

        super().set(key, (value, exp_time))
        self._clean = False
