import os
import subprocess
import sys

import click

from kks.util.testing import Test

GCC_ARGS = [
    'gcc',
    '-std=gnu11',
    '-g',
    '-Werror',
    '-Wall',
    '-Wextra',
    '-ftrapv',                    # catch signed overflow on addition, subtraction, multiplication operations
]

ASAN_ARGS = [
    '-fsanitize=address',
    '-fsanitize=undefined',
    '-fno-sanitize-recover=all',  # for RE in case of UB
]

ASAN_ENV = {
    'ASAN_OPTIONS': 'color=always',
}

LINK_ARGS = [
    '-lm',
]

VALGRIND_ARGS = [
    'valgrind',
    '--leak-check=full',
]


def compile_solution(directory, options):
    c_files = list(directory.glob('*.c'))

    if len(c_files) == 0:
        click.secho('No .c files found', fg='yellow', err=True)
        return None

    click.secho('Compiling... ', fg='green', err=True, nl=False)

    binary = compile_c(directory, c_files, options)

    if binary is None:
        click.secho('Compilation failed!', fg='red', err=True)
        return None

    binary_name = click.style(binary.relative_to(directory).as_posix(), fg='red', bold=True)
    click.secho(f'Successfully compiled binary {binary_name}', fg='green', err=True)

    return binary


def compile_c(workdir, files, options):
    filenames = [path.relative_to(workdir) for path in files]

    command = GCC_ARGS
    if options.asan:
        command += ASAN_ARGS
    command += filenames
    command += LINK_ARGS

    p = subprocess.run(command, cwd=workdir)

    if p.returncode != 0:
        return None

    return workdir / 'a.out'


def run_solution(binary, args, options, test_data, capture_output=True):
    args = [binary.absolute()] + args

    env = os.environ
    if options.asan:
        env = dict(env, **ASAN_ENV)

    if options.valgrind:
        args = VALGRIND_ARGS + args

    if test_data.test_type == Test.TYPE_FILE:
        with test_data.input_file.open('rb') as f_in:
            process = subprocess.run(args, env=env, stdin=f_in, capture_output=capture_output)
    elif test_data.test_type == Test.TYPE_DATA:
        process = subprocess.run(args, env=env, input=test_data.input_data, capture_output=capture_output)
    elif test_data.test_type == Test.TYPE_STDIN:
        process = subprocess.run(args, env=env, stdin=sys.stdin, capture_output=capture_output)
    else:
        raise Exception('Unknown test type')

    return process

