import subprocess
from pathlib import Path

import click
from tqdm import tqdm

from kks.binary import compile_solution
from kks.util import get_solution_directory, print_diff, find_test_output, format_file, test_number_to_name, \
    find_test_pairs


@click.command(short_help='Test solutions')
@click.option('-s', '--sample', is_flag=True,
              help='Test only sample')
@click.option('-t', '--test', 'tests', type=int, multiple=True,
              help='Test numbers to run (multiple are allowed)')
@click.option('-r', '--range', 'test_range', type=int, nargs=2,
              help='Tests to run')
@click.option('-f', '--file', 'files', type=click.Path(), multiple=True,
              help='Test files')
@click.option('-c', '--continue', 'cont', is_flag=True,
              help='Continue running after error')
def test(tests, test_range, files, sample, cont):
    """
    Test solution

    \b
    Example usage:
        kks test
        kks test -s
        kks test -t 0 -t 2 -t 3
    """

    files = [Path(f) for f in files]

    directory = get_solution_directory()
    if directory is None:
        return

    binary = compile_solution(directory)
    if binary is None:
        return

    tests = find_tests_to_run(directory, files, tests, test_range, sample)
    if tests is None:
        return

    if not tests:
        click.secho('No tests found!', fg='red')
        return

    successful_count = 0
    ran_count = 0

    t = tqdm(tests, leave=False)
    for input_file, output_file in t:
        if sample:
            t.clear()
            with input_file.open('r') as f:
                input_data = f.read()
            click.secho("Sample input:", bold=True)
            click.secho(input_data)
            with output_file.open('r') as f:
                output_data = f.read()
            click.secho("Sample output:", bold=True)
            click.secho(output_data)

        t.set_description(f'Running {format_file(input_file)}')

        is_success = run_test(binary, input_file, output_file)

        ran_count += 1
        successful_count += is_success

        if not cont and not is_success:
            t.close()
            break

    color = 'red' if ran_count != successful_count else 'green'
    click.secho(f'Tests passed: {successful_count}/{ran_count}', fg=color, bold=True)


def run_test(binary, input_file, output_file):
    with input_file.open('r') as input_f:
        process = subprocess.run([binary.absolute()], stdin=input_f, capture_output=True)

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


def find_tests_to_run(directory, files, tests, test_range, sample):
    """
    Возвращает тесты для команды test
    :param directory: Папка задачи
    :param files: Входные файлы тестов
    :param tests: Номера тестов
    :param test_range: Промежуток номеров тестов
    :param sample: Вернуть только семпл
    :return: Пары (input, output)
    """

    result = set()

    need_files = not sample and len(files) != 0
    need_numbers = not sample and tests or test_range

    # need file tests
    if need_files:
        for input_file in files:
            if not input_file.is_file():
                click.secho(f'File {format_file(input_file)} not found', fg='red', err=True)
                return None
            output_file = find_test_output(input_file)
            if output_file is None:
                click.secho(f'No output for test file {format_file(input_file)}', fg='yellow', err=True)
                continue
            result.add((input_file, output_file))

    test_names = None

    # number tests
    if need_numbers:
        test_numbers = list(tests)
        if test_range:
            l, r = sorted(test_range)
            test_numbers += list(range(l, r + 1))

        if sample:
            test_numbers += [0]

        test_names = [test_number_to_name(number) for number in test_numbers]

    if sample:
        test_names = ['000']

    # need numbers or need all
    if need_numbers or not need_files:
        tests_dir = directory / 'tests'
        if not tests_dir.is_dir():
            click.secho(f'Not a directory: {format_file(tests_dir)}', fg='red', err=True)
            return None

        for input_file, output_file in find_test_pairs(tests_dir, test_names):
            if output_file is not None:
                result.add((input_file, output_file))
            else:
                click.secho(f'Test {format_file(input_file)} has no output', fg='yellow', err=True)

    return sorted(result)
