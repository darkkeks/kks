import difflib
import subprocess

import click

from kks.binary import compile_solution
from kks.util import get_solution_directory


@click.command(short_help='Test solutions')
@click.argument('contest', required=False)
@click.argument('task', required=False)
@click.option('-m', '--mode', default='auto', type=click.Choice(['auto'], case_sensitive=False))
def test(contest, task, mode):
    """Test solution

    Example usage:

    """

    if (contest is None) != (task is None):
        click.secho('Contest and task should both be specified', fg='red', err=True)
        return

    directory = get_solution_directory(contest, task)

    if directory is None:
        return

    binary = compile_solution(directory, mode)

    if binary is None:
        return

    tests_dir = directory / 'tests'

    if not tests_dir.exists():
        click.secho('No tests directory', fg='red', err=True)

    input_files = tests_dir.glob('*.in')
    input_files = sorted(input_files, key=lambda file: file.name)

    for input_file in input_files:
        test_name = input_file.stem
        output_file = tests_dir / (test_name + '.out')

        styled_file = click.style(input_file.name, fg='blue', bold=True)

        if not output_file.is_file():
            click.secho('No output file for test ' + styled_file, fg='yellow', err=True)
            continue

        click.secho('Running test ' + styled_file + '\t', err=True, nl=False)

        if not run_test(binary, input_file, output_file):
            break


def run_test(binary, input_file, output_file):
    with input_file.open('r') as input_f:
        process = subprocess.run(binary, stdin=input_f, capture_output=True)

    if process.returncode != 0:
        click.secho('RE', fg='red', bold=True)
        click.secho(f'Process exited with core {process.returncode}', fg='red')
        return False

    with output_file.open('r') as output_f:
        expected_output = output_f.read()

    actual_output = process.stdout.decode('utf-8')

    if expected_output != actual_output:
        click.secho('WA', fg='red', bold=True)

        expected_lines = expected_output.splitlines(keepends=True)
        actual_lines = actual_output.splitlines(keepends=True)
        diff = difflib.unified_diff(expected_lines, actual_lines, 'expected', 'actual')
        for line in diff:
            add = line.startswith('+')
            remove = line.startswith('-')
            color = 'red' if remove else 'green' if add else None
            click.secho(line, nl=False, fg=color)
        click.secho()
        return False

    click.secho('OK', fg='green', bold=True)
    return True






