from pathlib import Path

import click
from tqdm import tqdm

from kks.binary import compile_solution, run_solution
from kks.util.script import find_script
from kks.util.testing import TestSource, VirtualTestSequence, RunOptions, Test
from kks.util.common import get_solution_directory, format_file, find_test_output, \
    test_number_to_name, find_test_pairs, print_diff


@click.command(name='test', short_help='Test solutions')
@click.option('-T', '-tg', '--target', default='default',
              help='Target name to build')
@click.option('-v', '--verbose', is_flag=True,
              help='Verbose mode (show used compiler args)')
@click.option('-t', '--test', 'tests', type=int, multiple=True,
              help='Test numbers to run (multiple are allowed)')
@click.option('-r', '--range', 'test_range', type=int, nargs=2,
              help='Tests to run')
@click.option('-f', '--file', 'files', type=click.Path(), multiple=True,
              help='Test files')
@click.option('-s', '--sample', is_flag=True,
              help='Test only sample')
@click.option('-c', '--continue', 'continue_on_error', is_flag=True,
              help='Continue running after error')
@click.option('-i', '--ignore-exit-code', is_flag=True,
              help='Dont fail on non-zero exit code')
@click.option('--asan/--no-asan', is_flag=True, default=None,
              help='Use asan (true by default)')
@click.option('-g', '-vg', '--valgrind', is_flag=True,
              help='Use valgrind (disables asan)')
@click.option('-V', '-vt', '--virtual', is_flag=True,
              help='Use virtual tests (generate tests in memory)')
@click.option('--generator', type=click.Path(exists=True),
              help='generator for virtual tests (see "kks gen")')
@click.option('--solution', type=click.Path(exists=True),
              help='solution for virtual tests')
def test_(target, verbose, tests, test_range, files, sample,
          continue_on_error, ignore_exit_code, asan, valgrind,
          virtual, generator, solution):
    """
    Test solution

    \b
    Example usage:
        kks test
        kks test -s
        kks test -t 0 -t 2 -t 3
    """

    directory = get_solution_directory()

    options = RunOptions(
        continue_on_error=continue_on_error,
        ignore_exit_code=ignore_exit_code,
        asan=asan and not valgrind,
        valgrind=valgrind,
        is_sample=sample,
    )

    binary = compile_solution(directory, target, verbose, options)
    if binary is None:
        return

    if not virtual:
        files = [Path(f) for f in files]

        tests = find_tests_to_run(directory, files, tests, test_range, sample)
        if tests is None:
            return

        if len(tests) == 0:
            click.secho('No tests to run!', fg='red')
            return

        run_tests(binary, tests, options)
    else:
        generator = find_script(directory, 'gen', default=generator)
        solution = find_script(directory, 'solve', default=solution)
        with TestSource(generator, solution, options) as test_source:
            if test_range:
                l, r = sorted(test_range)
                test_range = range(l, r + 1)

            if not tests and not test_range:
                test_range = range(1, 101)

            all_tests = sorted(set(tests) | set(test_range or []))

            tests = VirtualTestSequence(test_source, all_tests)

            run_tests(binary, tests, options)


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
                click.secho(
                    f'No output for test file {format_file(input_file)}', fg='yellow', err=True
                )
                continue
            result.add(Test.from_file(input_file.stem, input_file, output_file))

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
                result.add(Test.from_file(input_file.stem, input_file, output_file))
            else:
                click.secho(f'Test {format_file(input_file)} has no output', fg='yellow', err=True)

    return sorted(result, key=lambda test: test.name)


def run_tests(binary, tests, options):
    successful_count = 0
    ran_count = 0

    t = tqdm(tests, leave=False)
    for test in t:
        if options.is_sample:
            t.clear()
            input_data = test.read_input()
            click.secho("Sample input:", bold=True)
            click.secho(input_data.decode())
            output_data = test.read_output()
            click.secho("Sample output:", bold=True)
            click.secho(output_data.decode())

        t.set_description(f'Running {format_file(test.name)}')

        is_success = run_test(binary, options, test)

        ran_count += 1
        successful_count += is_success

        if not options.continue_on_error and not is_success:
            t.close()
            break

    color = 'red' if ran_count != successful_count else 'green'
    click.secho(f'Tests passed: {successful_count}/{ran_count}', fg=color, bold=True)


def run_test(binary, options, test):
    process = run_solution(binary, [], options, test)

    if process.returncode != 0 and not options.ignore_exit_code:
        error_output = process.stderr.decode('utf-8')
        click.secho(f'RE {test.name}', fg='red', bold=True)
        click.secho(f'Process exited with code {process.returncode}', fg='red')
        if error_output:
            click.secho(error_output)
        return False

    expected_output = test.read_output()
    actual_output = process.stdout

    if expected_output != actual_output:
        click.secho(f'WA {test.name}', fg='red', bold=True)
        try:
            expected = expected_output.decode('utf-8')
            actual = actual_output.decode('utf-8')
            print_diff(expected, actual, 'expected', 'actual')
            click.secho()
        except UnicodeDecodeError:
            click.secho('Output differs, but cant be decoded as utf-8', fg='red')
        return False

    return True
