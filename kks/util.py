import configparser
import pickle
from pathlib import Path

import click
import requests

from kks.ejudge import AuthData, ejudge_auth, check_session


def config_directory():
    directory = Path(click.get_app_dir('kks', force_posix=True))
    directory.mkdir(exist_ok=True)
    return directory


def read_config():
    config = configparser.ConfigParser()
    config.optionxform = str
    cfg = config_directory() / 'config.ini'
    if cfg.is_file():
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
    cookies = config_directory() / 'cookies.pickle'
    if not cookies.is_file():
        return None

    session = requests.session()
    with open(cookies, 'rb') as f:
        try:
            cookies = pickle.load(f)
        except Exception:
            return None
        session.cookies.update(cookies)
    return session


def save_auth_data(auth_data, store_password=True):
    config = read_config()
    config['Auth'] = {
        'login': auth_data.login,
        'contest': auth_data.contest_id
    }

    if store_password and auth_data.password is not None:
        config['Auth']['password'] = auth_data.password

    write_config(config)


def load_auth_data():
    config = read_config()
    if not config.has_section('Auth'):
        return None
    auth = config['Auth']
    if 'login' in auth and 'contest' in auth:
        return AuthData(auth['login'], auth['contest'], auth.get('password', None))
    return None


def save_links(links):
    config = read_config()
    config['Links'] = links
    write_config(config)


def load_links():
    config = read_config()
    if config.has_section('Links'):
        return config['Links']
    return None


def get_valid_session():
    session = load_session()

    if session is not None:
        links = load_links()
        if links is None or not check_session(links, session):
            session = None

    if session is None:
        auth_data = load_auth_data()
        if auth_data is None:
            click.secho('No valid cookies or auth data, please use "kks auth" to log in', fg='yellow', err=True)
            return None

        click.secho('Cookies are either missing or invalid, trying to auth with saved data', fg='yellow', err=True)
        store_password = True
        if auth_data.password is None:
            store_password = False
            auth_data.password = click.prompt('Password', hide_input=True)

        session = requests.session()
        links = ejudge_auth(auth_data, session)
        if links is None:
            return None

        save_auth_data(auth_data, store_password)
        save_links(links)
        store_session(session)

    return session


def get_clang_style_string():
    cfg = config_directory() / '.clang-format'
    if cfg.exists():
        with cfg.open('r') as f:
            return f.read()

    return r"""{
        Language: Cpp,
        BasedOnStyle: Google,
        IndentWidth: 4,
        UseTab: Never,
        NamespaceIndentation: All,
        ColumnLimit: 80,
        AccessModifierOffset: -4,
        AlignAfterOpenBracket: AlwaysBreak,
        AlignOperands: false,
        AlwaysBreakTemplateDeclarations: Yes,
        BinPackArguments: false,
        BinPackParameters: false,
        AllowShortFunctionsOnASingleLine: Empty,
        BreakBeforeBraces: Custom,
        BraceWrapping: { AfterEnum: true, AfterStruct: true }
    }"""


def find_workspace(path=None):
    if path is None:
        path = Path()

    path = path.resolve()

    while path.is_dir():
        file = path / '.kks-workspace'
        if file.exists():
            return path
        if path == path.parent:
            return None
        path = path.parent


def get_solution_directory():
    workspace = find_workspace()

#     if contest is not None and task is not None:
#         if workspace is not None:
#             result = workspace
#
#             if not result.is_dir():
#                 click.secho(f'Path {result} is not a directory', fg='red', err=True)
#                 return None
#
#             return result
#         else:
#             click.secho('Could not find workspace', fg='red', err=True)
#             return None

    return Path().absolute()
