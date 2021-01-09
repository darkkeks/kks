import configparser
import difflib
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
    return Path()


def print_diff(before_output, after_output, before_name, after_name):
    expected_lines = before_output.splitlines(keepends=True)
    actual_lines = after_output.splitlines(keepends=True)
    diff = difflib.unified_diff(expected_lines, actual_lines, before_name, after_name)
    for line in diff:
        add = line.startswith('+')
        remove = line.startswith('-')
        color = 'red' if remove else 'green' if add else None
        click.secho(line, nl=False, fg=color)
        if not line.endswith('\n'):
            click.secho('\n\\ No newline at end of file')


def format_file(file):
    if isinstance(file, Path):
        file = file.as_posix()
    return click.style(file, fg='blue', bold=True)


def test_number_to_name(number):
    return str(number).rjust(3, '0')


IN_EXT = ['.in', '', '.dat']
OUT_EXT = ['.out', '.a', '.ans']


def get_matching_suffix(in_ext):
    pos = IN_EXT.index(in_ext)
    return OUT_EXT[pos]


def find_test_pairs(directory, names=None):
    """
    Находит пары тестов (input, output) такие, что у них совпадают названия
    Выходной файл может быть None, если нашли только входной
    :param directory: Папка, в которой ищем тесты
    :param names: Если не None, то тесты фильтруются по имени
    """
    in_files = []
    out_files_by_stem = {}

    if names is None:
        files = directory.glob('*')
    else:
        files = [
            (directory / name).with_suffix(ext)
            for name in names
            for ext in IN_EXT + OUT_EXT
        ]

    for file in files:
        if file.is_file():
            suffix = file.suffix
            if suffix in IN_EXT:
                in_files.append(file)
            if suffix in OUT_EXT:
                out_files_by_stem[file.stem] = file

    for file in in_files:
        matching = file.with_suffix(get_matching_suffix(file.suffix))
        if matching.is_file():
            yield file, matching
        elif file.stem in out_files_by_stem:
            yield file, out_files_by_stem[file.stem]
        else:
            yield file, None


def find_test_output(input_file):
    matching = input_file.with_suffix(get_matching_suffix(input_file.suffix))
    if matching.is_file():
        return matching
    for ext in OUT_EXT:
        output_file = input_file.with_suffix(ext)
        if output_file.is_file():
            return output_file
    return None


def prompt_choice(text, options):
    """Return the index of user's choice (0 ... len(options) - 1)"""
    click.secho(f'{text}:')
    for index, option in enumerate(options, start=1):
        click.secho(f'{index:>4}) {option}')
    return click.prompt('', prompt_suffix='> ', type=click.IntRange(min=1, max=len(options))) - 1


def write_contests(workspace, contests):
    hidden = get_hidden_dir(workspace)
    if not hidden.exists():
        hidden.mkdir()
    index_file = hidden / '.index'
    with open(index_file, 'wb') as f:
        pickle.dump(contests, f)


def read_contests(workspace):
    index_file = get_hidden_dir(workspace) / '.index'
    if not index_file.exists():
        return set()
    with open(index_file, 'rb') as f:
        return pickle.load(f)


def get_hidden_dir(workspace):
    return workspace / '.kks-contests'


def get_contest_dir(workspace, contest):
    c_dir = get_hidden_dir(workspace) / contest
    if c_dir.exists():
        return c_dir
    return workspace / contest  # may not exist!


def get_task_dir(workspace, contest, number):
    return get_contest_dir(workspace, contest) / number
