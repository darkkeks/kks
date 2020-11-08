import subprocess
import sys

import click

from kks.binary import compile_solution
from kks.util import get_solution_directory


@click.command(short_help='Run solution')
@click.option('-m', '--mode', default='auto', type=click.Choice(['auto'], case_sensitive=False))
@click.argument('run_args', nargs=-1, type=click.UNPROCESSED)
def run(mode, run_args):
    """Run solution

    Example usage:

      kks run

      kks run < tests/000.in

      kks run sm01 1 > output.txt

      kks run sm01 1  argument_1 argument_2
    """

    directory = get_solution_directory()

    if directory is None:
        return

    binary = compile_solution(directory, mode)

    if binary is None:
        return

    output = f'Running binary'
    if len(run_args) > 0:
        output += ' with arguments ' + click.style(' '.join(run_args), fg='red', bold=True)
    click.secho(output, fg='green', err=True)

    run_binary(binary, run_args)


def run_binary(binary, args):
    subprocess.run([binary] + list(args), stdin=sys.stdin)


