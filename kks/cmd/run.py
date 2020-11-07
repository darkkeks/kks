import subprocess
import sys
from pathlib import Path

import click
import colorama

from kks.compile import compile_c
from kks.util import find_workspace


@click.command()
@click.argument('contest', required=False)
@click.argument('task', required=False)
@click.option('-m', '--mode', default='c', type=click.Choice(['c'], case_sensitive=False))
@click.argument('run_args', nargs=-1, type=click.UNPROCESSED)
def run(contest, task, mode, run_args):
    """Run solution"""

    if (contest is None) != (task is None):
        click.secho('Contest and task should both be specified', fg='red', err=True)
        return

    directory = get_solution_directory(contest, task)

    if directory is None:
        return

    if mode != 'c':
        click.secho(f'Unknown run mode {mode}', fg='yellow', err=True)
        return

    c_files = list(directory.glob('*.c'))

    if len(c_files) == 0:
        click.secho('No .c files found', fg='yellow', err=True)
        return

    click.secho('Compiling...', fg='green', err=True)

    binary = compile_c(directory, c_files)

    if binary is None:
        click.secho('Compilation failed!', fg='red', err=True)
        return

    binary_name = click.style(binary.relative_to(directory).as_posix(), fg='red', bold=True)
    click.secho(f'Successfully compiled binary {binary_name}', fg='green', err=True)

    output = f'Running binary'
    if len(run_args) > 0:
        output += ' with arguments ' + click.style(' '.join(run_args), fg='red', bold=True)
    click.secho(output, fg='green', err=True)

    run_binary(binary, run_args)


def run_binary(binary, args):
    subprocess.run([binary] + list(args), stdin=sys.stdin)


def get_solution_directory(contest, task):
    workspace = find_workspace()

    if contest is not None and task is not None:
        if workspace is not None:
            result = workspace / contest / task

            if not result.is_dir():
                click.secho(f'Path {result} is not a directory', fg='red', err=True)
                return None

            return result
        else:
            click.secho('Could not find workspace', fg='red', err=True)
            return None

    return Path().absolute()
