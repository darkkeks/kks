import subprocess

import click
from tqdm import tqdm

from kks.binary import compile_solution
from kks.util import get_solution_directory, print_diff, find_tests


@click.command(short_help='Test solutions')
@click.option('-m', '--mode', default='auto', type=click.Choice(['auto'], case_sensitive=False))
@click.option('-s', '--sample', is_flag=True,
              help='Test only sample')
@click.option('-t', '--test', 'tests', multiple=True,
              help='Run specific tests')
def test(mode, tests, sample):
    """
    Test solution

    \b
    Example usage:
        kks test
        kks test -s
        kks test -t 0 -t 2 -t 3
    """

    directory = get_solution_directory()
    if directory is None:
        return

    binary = compile_solution(directory, mode)
    if binary is None:
        return

    input_files = find_tests(directory, tests, sample)
    if input_files is None:
        return

    if len(input_files) == 0:
        click.secho('No tests found!', fg='red')
        return

    t = tqdm(input_files, leave=False)
    for input_file in t:
        output_file = input_file.with_suffix('.out')

        styled_file = click.style(input_file.as_posix(), fg='blue', bold=True)

        if not output_file.is_file():
            t.clear()
            click.secho(f'No output file for test {styled_file}, skipping', fg='yellow', err=True)
            continue

        if sample:
            t.clear()
            with input_file.open('r') as f:
                input_data = f.read()
            with output_file.open('r') as f:
                output_data = f.read()
            click.secho("Sample input:", bold=True)
            click.secho(input_data)
            click.secho("Sample output:", bold=True)
            click.secho(output_data)

        t.set_description(f'Running {styled_file}')

        if not run_test(binary, input_file, output_file):
            t.close()
            return

    click.secho('All tests passed!', fg='green')


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
        print_diff(expected_output, actual_output, 'expected', 'actual')
        click.secho()
        return False

    return True






