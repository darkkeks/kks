from pathlib import Path

import click

from kks.binary import compile_solution
from kks.testing import Generator, Checker
from kks.util import get_solution_directory, find_test_output, format_file, test_number_to_name, find_test_pairs


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
@click.option('-vg', '--valgrind', is_flag=True,
              help='Use valgrind')
@click.option('-vt', '--virtual', is_flag=True,
              help='Use virtual tests (generate tests in memory)')
@click.option('-gen', '--generator', type=click.Path(exists=True),
              help='generator for virtual tests (see "kks gen")')
@click.option('-sol', '--solution', type=click.Path(exists=True),
              help='solution for virtual tests')
def test(tests, test_range, files, sample, cont, valgrind, virtual, generator, solution):
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

    checker = Checker(cont, valgrind)
    binary = compile_solution(directory)
    if binary is None:
        return

    if virtual:
        generator = Path(generator or directory / 'gen.py')
        solution = Path(solution or directory / 'solve.py')
        gen = Generator(generator, solution)

        if test_range:
            l, r = sorted(test_range)
            test_range = range(l, r + 1)

        if not tests and not test_range:
            test_range = range(1, 101)

        all_tests = sorted(set(tests) | set(test_range))
        checker.run_virtual(binary, gen, all_tests)

    else:
        files = [Path(f) for f in files]

        tests = find_tests_to_run(directory, files, tests, test_range, sample)
        if tests is None:
            return

        if not tests:
            click.secho('No tests found!', fg='red')
            return

        checker.run_tests(binary, tests, sample)


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
