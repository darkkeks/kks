from pathlib import Path
from sys import exit

import click

from kks.binary import compile_solution, run_solution
from kks.util.testing import RunOptions, Test
from kks.util.common import get_solution_directory, find_test_pairs, format_file, test_number_to_name


@click.command(short_help='Run solution')
@click.option('-T', '-tg', '--target', default='default',
              help='Target name to build')
@click.option('-v', '--verbose', is_flag=True,
              help='Verbose mode (show used compiler args)')
@click.option('--asan/--no-asan', is_flag=True, default=None,
              help='Use asan (true by default)')
@click.option('-g', '-vg', '--valgrind', is_flag=True,
              help='Use valgrind (disables asan)')
@click.option('-s', '--sample', is_flag=True,
              help='Run on sample test')
@click.option('-t', '--test', 'test',
              help='Test number to pass as input')
@click.option('-f', '--file', 'file', type=click.Path(exists=True),
              help='File to use as an input')
@click.argument('run_args', nargs=-1, type=click.UNPROCESSED)
def run(asan, valgrind, sample, test, file, target, verbose, run_args):
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

    options = RunOptions(
        asan=asan and not valgrind,
        valgrind=valgrind,
    )

    binary = compile_solution(directory, target, verbose, options)
    if binary is None:
        return

    test_data = find_test_to_run(directory, test, file, sample)
    if test_data is None:
        return

    if len(run_args) > 0:
        click.secho(
            click.style('Running binary with arguments ', fg='green') +
            click.style(' '.join(run_args), fg='red', bold=True),
            err=True
        )

    exit(run_solution(binary, list(run_args), options, test_data, capture_output=False).returncode)


def find_test_to_run(directory, test, file, sample):
    has_file = file is not None
    has_test = test is not None

    if sum([sample, has_file, has_test]) > 1:
        click.secho(
            "Specify either test, file or sample to use as input, not multiple",
            fg='red', err=True
        )
        return None

    if has_file:
        return Test.from_file(None, Path(file), None)
    elif sample:
        test_names = ['000']
    elif has_test:
        test_names = {test, test_number_to_name(test)}
    else:
        return Test.from_stdin()

    tests_dir = directory / 'tests'
    if not tests_dir.is_dir():
        click.secho(f'Not a directory: {format_file(tests_dir)}', fg='red', err=True)
        return None

    tests = find_test_pairs(tests_dir, test_names)
    input_file, _ = next(tests, (None, None))

    if input_file is None:
        click.secho(
            f'Could not find tests with names {", ".join(test_names)} '
            f'in directory {format_file(tests_dir)}',
            fg='red', err=True
        )
        return None
    return Test.from_file(None, input_file, None)
