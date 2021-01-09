import shutil
import subprocess
import tempfile
from pathlib import Path

import click

from kks.util.common import get_solution_directory, get_clang_style_string, print_diff


@click.command(short_help='Lint solution')
@click.option('--diff/--no-diff', is_flag=True, default=True,
              help='Show lint diff. Always true for dry-run')
@click.option('-n', '--dry-run', is_flag=True, default=False,
              help='Dont actually change any files. Uses temporary directory')
def lint(diff, dry_run):
    """
    Lint solution in current task directory using clang-format.

    clang-format has to be present in PATH.

    If file ~/.kks/.clang-format exists, it will be passed to clang-format.
    Otherwise, default config (hardcoded in common.py) is used.
    """

    directory = get_solution_directory()
    if directory is None:
        return

    files = list(directory.glob('*.c')) + list(directory.glob('*.h')) + list(directory.glob('*.cpp'))

    if not files:
        click.secho('No .c, .h, .cpp files found', fg='yellow', err=True)
        return

    if dry_run:
        with tempfile.TemporaryDirectory(prefix='kks-') as work_directory:
            temp_files = [Path(shutil.copy(file, work_directory)) for file in files]
            format_files(temp_files, diff=True)
    else:
        format_files(files, diff=diff)
        click.secho(f'Successfully formatted!', fg='green', err=True)


def format_files(files, diff=True):
    before, after = {}, {}

    if diff:
        for file in files:
            with file.open('r') as f:
                before[file] = f.read()

    file_names = [file.as_posix() for file in files]

    files_string = click.style(' '.join(file_names), fg='blue', bold=True)
    click.secho('Formatting files ' + files_string)

    style_string = '--style=' + get_clang_style_string()
    process = subprocess.run(['clang-format', '-i', style_string] + file_names)

    if process.returncode != 0:
        click.secho(f'Clang-format exited with exit-code {process.returncode}', fg='red', err=True)
        return

    if diff:
        for file in files:
            with file.open('r') as f:
                after[file] = f.read()

        for file in files:
            print_diff(before[file], after[file], file.as_posix(), file.as_posix())
