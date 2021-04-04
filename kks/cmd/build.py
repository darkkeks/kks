import click

from kks.binary import compile_solution
from kks.util.common import get_solution_directory
from kks.binary import BuildOptions


@click.command(short_help='Build solution')
@click.option('-T', '-tg', '--target', default='default',
              help='Target name to build')
@click.option('-v', '--verbose', is_flag=True,
              help='Verbose mode (show used compiler args)')
@click.option('--asan/--no-asan', is_flag=True, default=None,
              help='Use asan (true by default)')
def build(target, verbose, asan):
    directory = get_solution_directory()

    options = BuildOptions(
        asan=asan,
        verbose=verbose
    )

    compile_solution(directory, target, options)
