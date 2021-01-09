import click
from tqdm import tqdm

from kks.util.testing import TestSource, RunOptions
from kks.util.common import get_solution_directory, test_number_to_name, find_test_pairs, get_matching_suffix, \
    format_file
from kks.util.script import find_script


@click.command(short_help='Generate tests')
@click.option('-o', '--output-only', is_flag=True,
              help='If specified, only solution will run. Useful to generate output for manually created tests')
@click.option('-g', '--generator', type=click.Path(exists=True),
              help='Script, used to generate .in files')
@click.option('-s', '--solution', type=click.Path(exists=True),
              help='Script, used to generate .out files')
@click.option('-t', '--test', 'tests', type=int, multiple=True,
              help='Test number to generate')
@click.option('-r', '--range', 'test_range', type=int, nargs=2,
              help='Tests to generate')
@click.option('-f', '--force', is_flag=True,
              help='Overwrite .in files')
@click.option('-i', '--ignore-exit-code', is_flag=True,
              help='Dont fail on non-zero exit code')
@click.argument('gen_args', nargs=-1, type=click.UNPROCESSED)
def gen(output_only, generator, solution, tests, test_range, force, ignore_exit_code, gen_args):
    """
    Generate tests

    \b
    Example usage:
      kks gen --test 17
      kks gen --range 1 100
      kks gen --test 12 --output-only
      kks gen --range 1 50 --force
      kks gen --generator gen.py --solution solve.py
    """

    directory = get_solution_directory()

    options = RunOptions(
        ignore_exit_code=ignore_exit_code
    )

    generator = find_script(directory, 'gen', default=generator, exists=not output_only)
    solution = find_script(directory, 'solve', default=solution)

    with TestSource(generator, solution, options) as test_source:
        test_pairs = find_tests_to_gen(directory, tests, test_range)
        test_pairs = sorted(test_pairs)

        generate_tests(test_source, test_pairs, output_only, force, gen_args)


def find_tests_to_gen(directory, tests, test_range):
    """
    Возвращает пары файлов, с которыми будем работать

    В gen можно передать конкретные названия тестов, либо промежуток тестов
    1) Если не передано ничего - используем [1; 100]
    2) Объединяем конкретные тесты и отрезок
    3) Пытаемся найти существующие файлы с нужными названиями
    4) Если нету, добавляем
    """
    tests_dir = directory / 'tests'
    tests_dir.mkdir(exist_ok=True)

    if not tests and not test_range:
        test_range = (1, 100)

    test_numbers = list(tests)
    if test_range:
        l, r = sorted(test_range)
        test_numbers += list(range(l, r + 1))

    test_names = [test_number_to_name(number) for number in test_numbers]

    pairs = list(find_test_pairs(tests_dir, test_names))

    used_names = [input_file.stem for input_file, _ in pairs]
    not_used_names = set(test_names) - set(used_names)

    def output_file_for_input_file(input_file):
        return input_file.with_suffix(get_matching_suffix(input_file.suffix))

    result = []

    # Существующие файлы (добавляем выходной, если его нету)
    result += [
        (input_file, output_file or output_file_for_input_file(input_file))
        for input_file, output_file in pairs
    ]

    # Если пары совсем не существует, добавляем
    result += [
        ((tests_dir / test_name).with_suffix('.in'),
         (tests_dir / test_name).with_suffix('.out'))
        for test_name in not_used_names
    ]

    return result


def generate_tests(test_source, test_pairs, output_only, force, gen_args):
    generated_tests = 0
    t = tqdm(test_pairs, leave=False)
    for input_file, output_file in t:
        if not output_only and input_file.exists() and not force:
            t.clear()
            click.secho(f'Input file {format_file(input_file)} ', fg='yellow', err=True, nl=False)
            click.secho(f'already exists, skipping. Specify -f to overwrite', fg='yellow', err=True)
            continue

        if output_only and not input_file.exists():
            t.clear()
            click.secho(f'Input file {format_file(input_file)} ', fg='red', err=True, nl=False)
            click.secho(f'does not exist, skipping', fg='red', err=True)
            continue

        if output_file and output_file.exists() and not force:
            t.clear()
            click.secho(f'Output file {format_file(output_file)} ', fg='yellow', err=True, nl=False)
            click.secho('already exists, skipping. Specify -f to overwrite', fg='yellow', err=True)
            continue

        t.set_description(f'Generating test {format_file(input_file)}')

        if not output_only:
            with input_file.open('wb') as f:
                if test_source.generate_input(input_file.stem, gen_args, stdout=f) is None:
                    return

        with input_file.open('rb') as f_in, output_file.open('wb') as f_out:
            if test_source.generate_output(input_file.stem, gen_args, stdin=f_in, stdout=f_out) is None:
                return

        generated_tests += 1

    click.secho(f'Generated {generated_tests} tests!', fg='green')
