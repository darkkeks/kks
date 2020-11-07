import configparser
import pickle
from pathlib import Path

import click
import requests


def config_directory():
    directory = Path(click.get_app_dir('kks', force_posix=True))
    directory.mkdir(exist_ok=True)
    return directory


def read_config():
    cfg = config_directory() / 'config.ini'
    config = configparser.ConfigParser()
    config.read(cfg)
    return config


def write_config(config):
    cfg = config_directory() / 'config.ini'
    with cfg.open('w') as f:
        config.write(f)


def store_session(session):
    cookies = config_directory() / 'cookies.pickle'
    with open(cookies, 'wb') as f:
        pickle.dump(session.cookies, f)


def load_session():
    session = requests.session()

    cookies = config_directory() / 'cookies.pickle'
    with open(cookies, 'wb') as f:
        session.cookies.update(pickle.load(f))

    return session
