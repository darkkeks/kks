import subprocess

import click

GCC_ARGS = [
    'gcc',
    '-g',
    '-Werror',
    '-Wall',
    '-Wextra',
    '-fsanitize=address',
    '-fsanitize=undefined',
    '-fno-sanitize-recover=all',  # for RE in case of UB
]

VALGRIND_ARGS = [
    'valgrind',
    '--leak-check=full',
]


def compile_solution(directory):
    c_files = list(directory.glob('*.c'))

    if len(c_files) == 0:
        click.secho('No .c files found', fg='yellow', err=True)
        return None

    click.secho('Compiling... ', fg='green', err=True, nl=False)

    binary = compile_c(directory, c_files)

    if binary is None:
        click.secho('Compilation failed!', fg='red', err=True)
        return None

    binary_name = click.style(binary.relative_to(directory).as_posix(), fg='red', bold=True)
    click.secho(f'Successfully compiled binary {binary_name}', fg='green', err=True)

    return binary


def compile_c(workdir, files):
    filenames = [path.relative_to(workdir) for path in files]

    command = GCC_ARGS + filenames
    p = subprocess.run(command, cwd=workdir)

    if p.returncode != 0:
        return None

    return workdir / 'a.out'
