import shutil
import tempfile
from pathlib import Path
from sys import exit
from typing import List

import click

from kks.util.common import get_solution_directory, get_clang_style_string, \
                            get_clang_tidy_config, print_diff
from kks.util.compat import subprocess
from kks.util.config import find_target


class SkippedError(Exception):
    pass


@click.command(short_help='Lint solution')
@click.option('--diff/--no-diff', is_flag=True, default=True,
              help='Show lint diff. Always true for dry-run')
@click.option('-n', '--dry-run', is_flag=True, default=False,
              help='Dont actually change any files. Uses temporary directory')
# Not sure if fixes work as intended when applied to multiple files.
# Also some checks (like readability-magic-numbers) just don't have any auto-fixes.
@click.option('-f', '--fix', is_flag=True, default=False,
              help='Apply clang-tidy fixes. Experimental, may break your code. '
                   'Always false for dry-run. If there are compiler errors, fixes are NOT applied.')
@click.option('-T', '-tg', '--target', default='default',
              help='Target name for clang-tidy compiler flags')  # Add --asan/--no-asan?
def lint(diff, dry_run, fix, target):
    """
    Lint solution in current task directory using clang-format and clang-tidy.

    clang-format and clang-tidy must be present in PATH.

    If file ~/.kks/.clang-format exists, it will be passed to clang-format.
    Otherwise, default config (hardcoded in common.py) is used.
    The same applies to clang-tidy.
    """

    directory = get_solution_directory()

    # Also finds C++ generators / reference solutions. Use target.files instead?
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
                click.secho('Successfully formatted!', fg='green', err=True)
    except SkippedError:
        pass
    try:
        lint_ok = run_clang_tidy(files, target, fix=fix and not dry_run)
        all_checks_passed &= lint_ok
        if lint_ok:
            click.secho('Clang-tidy checks passed!', fg='green', err=True)
    except SkippedError:
        pass
    exit(0 if all_checks_passed else 1)


def _run_binary(args):
    try:
        return subprocess.run(args)
    except FileNotFoundError:
        click.secho(f"'{args[0]}' is not in PATH", fg='yellow', err=True)
        raise SkippedError()


def _get_compiler_flags(source_files: List[Path], target_name: str):
    target = find_target(target_name)
    if target is None:
        click.secho(f'No target {target_name} found', fg='red', err=True)
        return None

    has_c = any(f.name.endswith('.c') for f in source_files)
    has_cpp = any(f.name.endswith('.cpp') for f in source_files)
    if has_c and has_cpp:
        # FIXME clang-tidy is skipped if solution is in C and gen/refsol is in C++
        click.secho('Cannot lint C and C++ together', fg='red', err=True)
        return None

    compiler = target.cpp_compiler if has_cpp else target.compiler
    std = target.cpp_std if has_cpp else target.std
    compiler_args = [compiler, '-std='+std] + target.flags

    if not target.asm64bit and any(f.suffix.lower() == '.s' for f in source_files):
        compiler_args.append('-m32')

    # Add ASAN_ARGS, filenames, libs? clang-tidy seems to work correctly without all these options
    return compiler_args


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


def run_clang_tidy(files: List[Path], target: str, fix: bool):
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

    compiler_flags = _get_compiler_flags(files, target)
    if compiler_flags is None:
        # internal error
        return True
    clang_tidy_args = ['clang-tidy', get_clang_tidy_config()]
    if fix:
        clang_tidy_args.append('--fix')
    process = _run_binary(clang_tidy_args + file_names + ['--'] + compiler_flags)

    if process.returncode not in [0, 1]:
        # killed / segfault / ???
        click.secho(f'Clang-tidy exited with code {process.returncode}', fg='red', err=True)
        return False

    return process.returncode == 0
