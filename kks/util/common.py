import difflib
import pickle
from abc import ABCMeta
from functools import wraps
from pathlib import Path
from time import time, sleep

import click

from kks.ejudge import AuthData


class Singleton(ABCMeta):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


def config_directory():
    directory = Path(click.get_app_dir('kks', force_posix=True))
    directory.mkdir(exist_ok=True)
    return directory


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


def find_problem_rootdir():
    cwd = Path.cwd().resolve()
    rootdir = find_workspace(cwd)
    if rootdir is None:
        return None
    hidden = get_hidden_dir(rootdir)
    try:
        _ = cwd.relative_to(hidden)
        rootdir = hidden
    except ValueError:
        pass
    parts = cwd.relative_to(rootdir).parts
    if len(parts) < 2:
        return None
    return rootdir / parts[0] / parts[1]


def with_retries(delay=0.5, multiplier=1.5, step=1, timeout=10):
    def decorator(func):
        initial_delay = delay

        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            overall_start = time()
            iteration = 1
            while True:
                start = time()
                result = func(*args, **kwargs)
                if result is not None:
                    return result
                elapsed = time() - start

                if time() - overall_start > timeout:
                    return None

                sleep(max(0, delay - elapsed))
                if iteration % step == 0:
                    delay *= multiplier
                iteration += 1

        return wrapper

    return decorator
