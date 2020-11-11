import subprocess
import sys

import click

from kks.binary import compile_solution
from kks.util import get_solution_directory, find_tests


@click.command(short_help='Run solution')
@click.option('-m', '--mode', default='auto', type=click.Choice(['auto'], case_sensitive=False),
              help='Compilation mode')
@click.option('-s', '--sample', is_flag=True,
              help='Run on sample test')
@click.option('-t', '--test', 'tests', multiple=True,
              help='Test number to pass as input')
@click.argument('run_args', nargs=-1, type=click.UNPROCESSED)
def run(mode, sample, tests, run_args):
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

    input_file = sys.stdin

    if len(tests) > 1:
        click.secho('Run only supports one --test option at a time', fg='red', err=True)
        return

    if sample or len(tests) != 0:
        tests = find_tests(directory, tests, sample, default_all=False)
        if tests is None:
            return

        input_file = tests[0].open('r')

    if len(run_args) > 0:
        output = f'Running binary with arguments ' + click.style(' '.join(run_args), fg='red', bold=True)
        click.secho(output, fg='green', err=True)

    subprocess.run([binary] + list(run_args), stdin=input_file)


