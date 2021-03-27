import gzip
import pickle
import sys
from configparser import ConfigParser
from datetime import datetime, timedelta
from io import BytesIO
from os import environ
from time import time

import click

from kks.util.common import Singleton, config_directory


class Section:
    """
    in config.ini all option names are lowercase and all underscores are replaced with dashes
    """
    def __init__(self, config, name):
        super().__setattr__('_config', config)
        super().__setattr__('_name', Section.canonical_name(name))

    @staticmethod
    def canonical_name(name):
        return name.capitalize()

    @staticmethod
    def to_option(name):
        return name.lower().replace('_', '-')

    def _convert(self, key, value):
        type_ = self.__annotations__[key]
        if type_ is bool:
            return self._config._convert_to_boolean(value)
        return type_(value)

    def _is_option(self, key):
        return key in super().__getattribute__('__annotations__')

    def _check_key(self, key):
        if not self._is_option(key):
            raise AttributeError(f'Option "{key}" is not allowed in config section "{self._name}"')

    def __getattribute__(self, key):
        if not super().__getattribute__('_is_option')(key):
            return super().__getattribute__(key)

        value = self._config.get(self._name, Section.to_option(key), fallback=None)
        if value is not None:
            return self._convert(key, value)
        return getattr(type(self), key, None)  # default

    def __setattr__(self, key, value):
        self._check_key(key)
        if not self._config.has_section(self._name):
            self._config.add_section(self._name)
        self._config.set(self._name, Section.to_option(key), str(value))

    def __delattr__(self, key):
        self._check_key(key)
        if not self._config.has_section(self._name):
            return
        self._config.remove_option(self._name, Section.to_option(key))


class EnvSection(Section):
    @staticmethod
    def to_envvar(name):
        return name.upper()

    def __getattribute__(self, key):
        if not super().__getattribute__('_is_option')(key):
            return super().__getattribute__(key)  # how to avoid second check?

        envvar = environ.get(EnvSection.to_envvar(key))
        if envvar is not None:
            return self._convert(key, envvar)
        return super().__getattribute__(key)


class AuthSection(Section):
    login: str
    password: str
    contest: int


class OptionsSection(EnvSection):
    save_html_statements: bool = True
    save_md_statements: bool = True
    mdwidth: int = 100
    max_kr: bool = False
    deadline_warning_days: int = 1
    global_opt_out: bool


class ConfigModel:
    auth: AuthSection
    options: OptionsSection


class Config(metaclass=Singleton):
    """global kks config"""

    def __init__(self):
        self._file = config_directory() / 'config.ini'
        self._config = ConfigParser()
        if self._file.is_file():
            self._config.read(self._file)
        # delete legacy section
        if self._config.has_section('Links'):
            self._config.remove_section('Links')
            self.save()

    def save(self):
        with self._file.open('w') as f:
            self._config.write(f)

    def reload(self):
        """force reload from disk"""
        if self._file.is_file():
            self._config.read(self._file)
        else:
            self._config.clear()

    def __getattribute__(self, key):
        if key in ConfigModel.__annotations__:
            section_type = ConfigModel.__annotations__[key]
            return section_type(self._config, key)
        return super().__getattribute__(key)

    def __delattr__(self, key):
        if key in ConfigModel.__annotations__:
            self._config.remove_section(Section.canonical_name(key))
        else:
            super().__delattr__(key)


class CompatUnpickler(pickle.Unpickler):

    class UniversalClass:
        def __init__(self, *args, **kwargs):
            pass

    def find_class(self, module, name):
        return CompatUnpickler.UniversalClass


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
            pickled_data_available = False
            try:
                with self._file.open('rb') as f:
                    data = f.read()
                if self.compress:
                    data = gzip.decompress(data)
                pickled_data_available = True
                self._data.update(pickle.loads(data))
            except Exception:
                if not (pickled_data_available and self._try_load_old(data)):
                    click.secho(f'Storage file {self._file} is corrupted', bg='red', err=True)
                    if click.confirm(click.style('Erase all saved data?', fg='red', bold=True)):
                        self._init_data(False)
                    else:
                        click.secho(f'You need to fix or delete {self._file.absolute()} manually', fg='red', err=True)
                        sys.exit()

        if self._data['__version__'] != self._version:
            click.secho(f'{self._file} uses an incompatible storage version, clearing saved data', bg='red', err=True)
            self._init_data(False)
        return self

    def _try_load_old(self, encoded):
        try:
            data = CompatUnpickler(BytesIO(encoded)).load()
            if isinstance(data, dict) and data['__version__'] != self._version:
                # just an old version, we may reset the storage
                self._data = data
                return True
            return False  # something is broken

        except Exception as e:
            return False

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
