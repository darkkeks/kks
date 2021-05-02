import click

from kks.binary import BuildOptions, compile_solution
from kks.util.common import get_solution_directory
from kks.util.targets import find_target


@click.command(short_help='Build solution')
@click.option('-T', '-tg', '--target', default='default',
              help='Target name to build')
@click.option('-v', '--verbose', is_flag=True,
              help='Verbose mode (show used compiler args)')
@click.option('--asan/--no-asan', is_flag=True, default=None,
              help='Use asan (true by default)')
def build(target, verbose, asan):
    directory = get_solution_directory()

    target = find_target(target)
    if target is None:
        return

    if asan is None:
        asan = target.default_asan

    options = BuildOptions(
        asan=asan,
        verbose=verbose
    )

    compile_solution(directory, target, options)
