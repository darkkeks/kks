import subprocess
import sys
from pathlib import Path

import click

from kks.binary import compile_solution, VALGRIND_ARGS
from kks.util import get_solution_directory, find_test_pairs, format_file, test_number_to_name


@click.command(short_help='Run solution')
@click.option('-vg', '--valgrind', is_flag=True,
              help='Use valgrind')
@click.option('-s', '--sample', is_flag=True,
              help='Run on sample test')
@click.option('-t', '--test', 'test',
              help='Test number to pass as input')
@click.option('-f', '--file', 'file', type=click.File(),
              help='File to use as an input')
@click.argument('run_args', nargs=-1, type=click.UNPROCESSED)
def run(valgrind, sample, test, file, run_args):
    """Run solution

    \b
    Example usage:
      kks run
      kks run -s
      kks run -t 10
      kks run -f tests/000.in
      kks run < tests/000.in > output.txt
      kks run -- arg_1 arg_2
    """

    directory = get_solution_directory()
    if directory is None:
        return

    binary = compile_solution(directory)
    if binary is None:
        return

    input_file = find_test_to_run(directory, test, file, sample)
    if input_file is None:
        return

    if isinstance(input_file, Path):
        input_file = input_file.open('r')

    if len(run_args) > 0:
        output = f'Running binary with arguments ' + click.style(' '.join(run_args), fg='red', bold=True)
        click.secho(output, fg='green', err=True)

    args = [binary.absolute()] + list(run_args)
    if valgrind:
        args = VALGRIND_ARGS + args
    subprocess.run(args, stdin=input_file)


def find_test_to_run(directory, test, file, sample):
    has_file = file is not None
    has_test = test is not None

    if sum([sample, has_file, has_test]) > 1:
        click.secho("Specify either test, file or sample to use as input, not multiple", fg='red', err=True)
        return None

    if has_file:
        return file
    elif sample:
        test_names = ['000']
    elif has_test:
        test_names = [test, test_number_to_name(test)]
    else:
        return sys.stdin

    tests_dir = directory / 'tests'
    if not tests_dir.is_dir():
        click.secho(f'Not a directory: {format_file(tests_dir)}', fg='red', err=True)
        return None

    tests = find_test_pairs(tests_dir, test_names)
    input_file, _ = next(tests, (None, None))

    if input_file is None:
        click.secho(f'Could not find tests with names {", ".join(test_names)} in directory {format_file(tests_dir)}',
                    fg='red', err=True)
    return input_file
