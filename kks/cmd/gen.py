import subprocess
from pathlib import Path

import click

from kks.util import get_solution_directory


@click.command(short_help='Run solution')
@click.option('-o', '--output-only', is_flag=True)
@click.option('-g', '--generator', type=click.Path(exists=True))
@click.option('-s', '--solution', type=click.Path(exists=True))
@click.option('-t', '--tests', type=click.IntRange(min=0, max=999), default=(1, 1000), nargs=2)
@click.option('-f', '--force', is_flag=True)
@click.argument('gen_args', nargs=-1, type=click.UNPROCESSED)
def gen(output_only, generator, solution, tests, force, gen_args):
    """Generate tests"""

    directory = get_solution_directory()

    generator = generator or directory / 'gen.py'
    solution = solution or directory / 'solve.py'

    if not generator.exists() and not output_only:
        click.secho(f'Generator {generator} does not exist', fg='red', err=True)
        return

    if not solution.exists():
        click.secho(f'Solution {solution} does not exist', fg='red', err=True)
        return

    l, r = tests
    if r < l:
        r, l = l, r

    tests_dir = directory / 'tests'
    tests_dir.mkdir(exist_ok=True)

    for i in range(l, r + 1):
        name = str(i).rjust(3, '0')
        click.secho('Generating test ' + click.style(name, fg='blue', bold=True))

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
