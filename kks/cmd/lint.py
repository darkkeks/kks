import shutil
import tempfile
from pathlib import Path
from sys import exit
from typing import List

import click

from kks.util.common import get_solution_directory, get_clang_style_string, \
                            get_clang_tidy_config, print_diff
from kks.util.compat import subprocess


class SkippedError(Exception):
    pass


@click.command(short_help='Lint solution')
@click.option('--diff/--no-diff', is_flag=True, default=True,
              help='Show lint diff. Always true for dry-run')
@click.option('-n', '--dry-run', is_flag=True, default=False,
              help='Dont actually change any files. Uses temporary directory')
@click.option('-T', '-tg', '--target', default='default',
              help='Target name for clang-tidy compiler flags')
def lint(diff, dry_run, target):
    """
    Lint solution in current task directory using clang-format and clang-tidy.

    clang-format and clang-tidy must be present in PATH.

    If file ~/.kks/.clang-format exists, it will be passed to clang-format.
    Otherwise, default config (hardcoded in common.py) is used.
    The same applies to clang-tidy.
    """

    directory = get_solution_directory()

    files = (
        list(directory.glob('*.c')) +
        list(directory.glob('*.h')) +
        list(directory.glob('*.cpp'))
    )

    if not files:
        click.secho('No .c, .h, .cpp files found', fg='yellow', err=True)
        return

    all_checks_passed = True
    try:
        if dry_run:
            with tempfile.TemporaryDirectory(prefix='kks-') as work_directory:
                temp_files = [Path(shutil.copy(file, work_directory)) for file in files]
                all_checks_passed &= format_files(temp_files, show_diff=True, diff_error=True)
        else:
            format_ok = format_files(files, show_diff=diff, diff_error=False)
            all_checks_passed &= format_ok
            if format_ok:
                click.secho(f'Successfully formatted!', fg='green', err=True)
    except SkippedError:
        pass
    try:
        # No auto-fixes yet (not sure if they will work as intended for multiple files).
        # Also some checks (like readability-magic-numbers) just don't have any auto-fixes.
        all_checks_passed &= run_clang_tidy(files, target)
    except SkippedError:
        pass
    exit(0 if all_checks_passed else 1)


def _run_binary(args):
    try:
        return subprocess.run(args)
    except FileNotFoundError:
        click.secho(f"'{args[0]}' is not in PATH", fg='yellow', err=True)
        raise SkippedError()


def format_files(files: List[Path], show_diff: bool, diff_error: bool) -> bool:
    """Runs clang-format on specified files.

    Args:
        files: A list of files to be formatted.
        show_diff: If True, print diff produced by clang-format.
        diff_error: If True, treat non-zero diff as error (return False).

    Returns: True if files are ok (no problems were found), False otherwise.

    Raises:
        SkippedError: clang-format is not in PATH.
    """
    before = {}

    if show_diff or diff_error:
        for file in files:
            with file.open('r') as f:
                before[file] = f.read()

    file_names = [file.as_posix() for file in files]

    files_string = click.style(' '.join(file_names), fg='blue', bold=True)
    click.secho('Formatting files ' + files_string)

    style_string = '--style=' + get_clang_style_string()
    process = _run_binary(['clang-format', '-i', style_string] + file_names)

    if process.returncode != 0:
        click.secho(f'Clang-format exited with code {process.returncode}', fg='red', err=True)
        return False

    if diff_error:
        diff_found = False

    if show_diff or diff_error:
        for file in files:
            with file.open('r') as f:
                after = f.read()
            if diff_error:
                diff_found |= after != before[file]
            if show_diff:
                print_diff(before[file], after, file.as_posix(), file.as_posix())

    if diff_error and diff_found:
        return False
    return True


def run_clang_tidy(files: List[Path], target: str):
    """Runs clang-tidy on specified files.

    Args:
        files: A list of files to be checked.
        target: Name of build target.

    Returns: True if files are ok (no problems were found), False otherwise.

    Raises:
        SkippedError: clang-tidy is not in PATH.
    """
    file_names = [file.as_posix() for file in files]

    files_string = click.style(' '.join(file_names), fg='blue', bold=True)
    click.secho('Linting files ' + files_string)

    process = _run_binary(['clang-tidy', get_clang_tidy_config()] + file_names + ['--'])  # TODO add args

    if process.returncode not in [0, 1]:
        # killed / segfault / ???
        click.secho(f'Clang-tidy exited with code {process.returncode}', fg='red', err=True)
        return False

    return process.returncode == 0
