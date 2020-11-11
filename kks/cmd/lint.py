import subprocess

import click

from kks.util import get_solution_directory, get_clang_style_string, print_diff


@click.command(short_help='Lint solution')
@click.option('--diff/--no-diff', is_flag=True, default=True,
              help='Show lint diff')
def lint(diff):
    """
    Lint solution in current task directory using clang-format.

    clang-format has to be present in PATH.

    If file ~/.kks/.clang-format exists, it will be passed to clang-format.
    Otherwise, default config (hardcoded in util.py) is used.
    """

    directory = get_solution_directory()
    if directory is None:
        return

    c_files = list(directory.glob('*.c'))
    if len(c_files) == 0:
        click.secho('No *.c files found', fg='yellow', err=True)
        return

    before = {}
    if diff:
        for file in c_files:
            with file.open('r') as f:
                before[file] = f.read()

    file_names = [file.as_posix() for file in c_files]

    files_string = click.style(' '.join(file_names), fg='blue', bold=True)
    click.secho('Formatting files ' + files_string)

    style_string = '--style=' + get_clang_style_string()
    process = subprocess.run(['clang-format', '-i', style_string] + file_names)

    if process.returncode != 0:
        click.secho(f'Clang-format exited with exit-code {process.returncode}', fg='red', err=True)
        return

    after = {}
    if diff:
        for file in c_files:
            with file.open('r') as f:
                after[file] = f.read()

        for file in c_files:
            print_diff(before[file], after[file], file.as_posix(), file.as_posix())

    click.secho(f'Successfully formatted!', fg='green', err=True)
