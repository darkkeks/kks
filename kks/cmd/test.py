from pathlib import Path
from typing import List, Set, Tuple, Optional

import click
from tqdm import tqdm

from kks.binary import compile_solution, run_solution
from kks.util.script import find_script
from kks.util.testing import TestSource, VirtualTestSequence, RunOptions, FileTest
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
        asan=asan if not valgrind else False,
        valgrind=valgrind,
        is_sample=sample,
    )

    binary = compile_solution(directory, target, verbose, options)
    if binary is None:
        return

    if virtual and not sample:
        generator = find_script(directory, 'gen', default=generator)
        if generator is None:
            return
        solution = find_script(directory, 'solve', default=solution)
        if solution is None:
            return
        with TestSource(generator, solution, options) as test_source:
            if test_range:
                l, r = sorted(test_range)
                test_range = range(l, r + 1)

            if not tests and not test_range:
                test_range = range(1, 101)

            all_tests = sorted(set(tests) | set(test_range or []))

            tests = VirtualTestSequence(test_source, all_tests)

            run_tests(binary, tests, options)
    else:
        files = [Path(f) for f in files]

        try:
            tests = find_tests_to_run(directory, files, tests, test_range, sample)
        except (FileNotFoundError, NotADirectoryError):
            return

        if len(tests) == 0:
            click.secho('No tests to run!', fg='red')
            return

        run_tests(binary, tests, options)


def find_tests_to_run(
    directory: Path,
    files: List[Path],
    tests: Tuple[int, ...],
    test_range: Optional[Tuple[int, int]],
    sample: bool
) -> List[FileTest]:
    """
    Возвращает тесты для команды test
    :param directory: Папка задачи
    :param files: Входные файлы тестов
    :param tests: Номера тестов
    :param test_range: Промежуток номеров тестов
    :param sample: Вернуть только семпл
    :return: Пары (input, output)
    :raises NotADirectoryError: `tests` не сузествует или не является директорией.
    :raises FileNotFoundError: Файл с входными данными для теста не найден.
    """

    def _find_tests_in_dir(test_names: Optional[List[str]]) -> Set[FileTest]:
        tests_dir = directory / 'tests'
        if not tests_dir.is_dir():
            click.secho(f'Not a directory: {format_file(tests_dir)}', fg='red', err=True)
            raise NotADirectoryError()

        # if there are duplicate files with different suffixes, ignore them
        found_tests: Set[FileTest] = set()
        for input_file, output_file in find_test_pairs(tests_dir, test_names):
            if output_file is not None:
                found_tests.add(FileTest(input_file.stem, input_file, output_file))
            else:
                click.secho(f'Test {format_file(input_file)} has no output', fg='yellow', err=True)
        return found_tests

    if sample:
        return list(_find_tests_in_dir(['000']))

    need_files = len(files) != 0
    need_numbers = tests or test_range

    # default - use all tests from the directory
    if not need_files and not need_numbers:
        return sorted(_find_tests_in_dir(None), key=lambda test: test.name)

    # use a set to avoid duplicate tests.
    # "kks test -t 1 -t 1 -r 1 1 -f tests/001.in" should run the test only once.
    result: Set[FileTest] = set()

    # add file tests, if any
    for input_file in files:
        if not input_file.is_file():
            click.secho(
                click.style('File ', fg='red') +
                format_file(input_file) +
                click.style(' not found', fg='red'),
                err=True
            )
            raise FileNotFoundError()
        output_file = find_test_output(input_file)
        if output_file is None:
            click.secho(
                f'No output for test file {format_file(input_file)}', fg='yellow', err=True
            )
            continue
        result.add(FileTest(input_file.stem, input_file, output_file))

    # add number tests (-t, -r)
    if need_numbers:
        test_numbers = set(tests)
        if test_range:
            l, r = sorted(test_range)
            test_numbers |= set(range(l, r + 1))

        test_names = [test_number_to_name(number) for number in test_numbers]
        result |= _find_tests_in_dir(test_names)

    return sorted(result, key=lambda test: test.name)


def run_tests(binary, tests, options):
    successful_count = 0
    ran_count = 0

    t = tqdm(tests, leave=False)
    for test in t:
        if options.is_sample:
            t.clear()
            input_data = test.get_input()
            click.secho("Sample input:", bold=True)
            click.secho(input_data.decode())
            output_data = test.get_output()
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

    expected_output = test.get_output()
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
