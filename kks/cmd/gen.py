import subprocess
from pathlib import Path

import click
from tqdm import tqdm

from kks.util import get_solution_directory, format_file, test_number_to_name, find_test_pairs, get_matching_suffix


@click.command(short_help='Generate tests')
@click.option('-o', '--output-only', is_flag=True,
              help='If specified, only solution will be run. Useful to generate output for manually created tests')
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
@click.argument('gen_args', nargs=-1, type=click.UNPROCESSED)
def gen(output_only, generator, solution, tests, test_range, force, gen_args):
    """
    Generate tests

    \b
    Example usage:
      kks gen -t 1337
      kks gen -r 1 100
      kks gen -t 1 -o
      kks gen -g gen.py -s solve.py -r 1 50 -f
    """

    directory = get_solution_directory()

    generator = Path(generator or directory / 'gen.py')
    solution = Path(solution or directory / 'solve.py')

    if not generator.exists() and not output_only:
        click.secho(f'Generator {generator} does not exist', fg='red', err=True)
        return

    if not solution.exists():
        click.secho(f'Solution {solution} does not exist', fg='red', err=True)
        return

    test_pairs = find_tests_to_gen(directory, tests, test_range)
    test_pairs = sorted(test_pairs)

    generated_tests = 0

    t = tqdm(test_pairs, leave=False)
    for input_file, output_file in t:
        if not output_only and input_file.exists() and not force:
            t.clear()
            click.secho(f'Input file ' + format_file(input_file), fg='yellow', err=True, nl=False)
            click.secho(f' already exists, skipping. Specify -f to overwrite', fg='yellow', err=True)
            continue

        if output_file and output_file.exists() and not force:
            t.clear()
            click.secho(f'Output file ' + format_file(output_file), fg='yellow', err=True, nl=False)
            click.secho(f' already exists, skipping. Specify -f to overwrite', fg='yellow', err=True)
            continue

        t.set_description(f'Generating test {format_file(input_file)}')

        if not output_only:
            with input_file.open('w') as f:
                args = [input_file.stem] + list(gen_args)
                if run_binary(generator, args, stdout=f) is None:
                    return

        with input_file.open('r') as f_in, output_file.open('w') as f_out:
            args = [input_file.stem]
            if run_binary(solution, args, stdin=f_in, stdout=f_out) is None:
                return

        generated_tests += 1

    click.secho(f'Generated {generated_tests} tests!', fg='green', err=True)


def find_tests_to_gen(directory, tests, test_range):
    """Находит существующие тесты"""
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

    # Добавляем выходной файл, если его не существует
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


def run_binary(binary, args, stdin=None, stdout=None):
    ext = binary.suffix

    interpreter = 'python3' if ext in ['.py', '.py3'] \
        else 'bash' if ext in ['.sh'] \
        else None

    if interpreter is None:
        click.secho(f'Cant run unrecognized script {format_file(binary)}', fg='red', err=True)
        return None

    process = subprocess.run([interpreter, binary] + args, stdin=stdin, stdout=stdout)

    if process.returncode != 0:
        click.secho('Script exited with code ' +
                    click.style(str(process.returncode), fg='red', bold=True) +
                    ' (args: ' + ' '.join(args) + ')', fg='yellow')
        return None

    return process
