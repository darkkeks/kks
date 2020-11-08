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
