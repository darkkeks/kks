import subprocess

import click
from tqdm import tqdm

from kks.util import get_solution_directory


@click.command(short_help='Run solution')
@click.option('-o', '--output-only', is_flag=True,
              help='If specified, only solution will be run. Useful to generate output for manually created tests')
@click.option('-g', '--generator', type=click.Path(exists=True),
              help='Script, used to generate .in files')
@click.option('-s', '--solution', type=click.Path(exists=True),
              help='Script, used to generate .out files')
@click.option('-t', '--test', type=int,
              help='Test number to generate')
@click.option('-r', '--range', 'test_range', type=int, nargs=2,
              help='Tests to generate')
@click.option('-f', '--force', is_flag=True,
              help='Overwrite .in files')
@click.argument('gen_args', nargs=-1, type=click.UNPROCESSED)
def gen(output_only, generator, solution, test, test_range, force, gen_args):
    """
    Generate tests

    Generate script is run with arguments "TEST_NUMBER GEN_ARGS". It's output is saved into .in file.

    Solution script is run with test number as argument, and .in file as stdin. It's output is saved into .out file.

    \b
    Example usage:
      kks gen -t 1337
      kks gen -r 1 100
      kks gen -t 1 -o
      kks gen -g gen.py -s solve.py -r 1 50 -f
    """

    directory = get_solution_directory()

    generator = generator or directory / 'gen.py'
    solution = solution or directory / 'solve.py'

    if not generator.exists() and not output_only:
        click.secho(f'Generator {generator} does not exist', fg='red', err=True)
        return

    if not solution.exists():
        click.secho(f'Solution {solution} does not exist', fg='red', err=True)
        return

    if test is not None and len(test_range) != 0:
        click.secho(f'Either test or range should be specified', fg='red', err=True)
        return

    if test is not None:
        test_numbers = [test]
    else:
        l, r = sorted(test_range or (1, 100))
        test_numbers = list(range(l, r + 1))

    tests_dir = directory / 'tests'
    tests_dir.mkdir(exist_ok=True)

    t = tqdm(test_numbers, leave=False)
    for i in t:
        name = str(i).rjust(3, '0')

        input_file = tests_dir / (name + '.in')
        output_file = tests_dir / (name + '.out')

        if output_only:
            if not input_file.exists():
                click.secho('Input file ' + click.style(input_file.name, fg='blue', bold=True) +
                            ' does not exists, skipping')
                continue
        else:
            if input_file.exists() and not force:
                click.secho('Input file ' + click.style(input_file.name, fg='blue', bold=True) +
                            ' already exists, skipping. Specify -f to overwrite')
                continue

            if output_file.exists() and not force:
                click.secho('Output file ' + click.secho(output_file.name, fg='blue', bold=True) +
                            ' already exists, skipping. Specify -f to overwrite')
                continue

        t.set_description('Generating test ' + click.style(name, fg='blue', bold=True))

        if not output_only:
            with input_file.open('w') as f:
                args = [str(i)] + list(gen_args)
                process = subprocess.run(['python3', generator] + args, stdout=f)
                if process.returncode != 0:
                    click.secho('Generator exited with code ' +
                                click.style(str(process.returncode), fg='red', bold=True) +
                                ' (args: ' + ' '.join(args) + ')', fg='yellow')

        with input_file.open('r') as f_in, output_file.open('w') as f_out:
            args = [str(i)]
            process = subprocess.run(['python3', solution] + args, stdin=f_in, stdout=f_out)
            if process.returncode != 0:
                click.secho('Solution exited with code ' +
                            click.style(str(process.returncode), fg='red', bold=True) +
                            ' (args: ' + ' '.join(args) + ')', fg='yellow')

    click.secho('Generated tests!', fg='green', err=True)
