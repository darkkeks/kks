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

    \b
    Example usage:
      kks run
      kks run < tests/000.in > output.txt
      kks run -- arg_1 arg_2
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

    subprocess.run([binary] + list(run_args), stdin=sys.stdin)
