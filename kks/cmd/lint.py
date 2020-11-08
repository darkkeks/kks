import subprocess

import click

from kks.util import get_solution_directory, get_clang_style_string


@click.command(short_help='Lint solution')
def lint():
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

    file_names = [file.as_posix() for file in c_files]

    files_string = click.style(' '.join(file_names), fg='blue', bold=True)
    click.secho('Formatting files ' + files_string)

    style_string = '--style=' + get_clang_style_string()
    process = subprocess.run(['clang-format', '-i', style_string] + file_names)

    if process.returncode != 0:
        click.secho(f'Clang-format exited with exit-code {process.returncode}', fg='red', err=True)
        return

    click.secho(f'Successfully formatted!', fg='green', err=True)
