import os
import subprocess
import sys
from itertools import chain

import click

from kks.util.config import find_target


GPP_ARGS = [
    'g++',
    '-std=gnu++17',
    '-g',
    '-O2',
    '-Werror',
    '-Wall',
    '-Wextra',
    '-ftrapv',
]

ASAN_ARGS = [
    '-fsanitize=address',
    '-fsanitize=undefined',
    '-fno-sanitize-recover=all',  # for RE in case of UB
]

ASAN_ENV = {
    'ASAN_OPTIONS': 'color=always',
}

VALGRIND_ARGS = [
    'valgrind',
    '--leak-check=full',
]


def compile_solution(directory, target_name, verbose, options):
    target = find_target(target_name)
    if target is None:
        click.secho(f'No target {target_name} found', fg='red', err=True)
        return None

    if verbose:
        click.secho(f'Selected target: {target}')

    if options.asan is None:
        options.asan = target.default_asan  # will be used in run_solution
    # gcc (clang) can compile c and asm files together, so everything should be ok
    source_files = list(chain(*[directory.glob(f) for f in target.files]))

    if len(source_files) == 0:
        click.secho('No source files found', fg='yellow', err=True)
        return None

    click.secho('Compiling... ', fg='green', err=True, nl=False)

    binary = compile_c(directory, source_files, target, verbose, options)

    if binary is None:
        click.secho('Compilation failed!', fg='red', err=True)
        return None

    binary_name = click.style(binary.relative_to(directory).as_posix(), fg='red', bold=True)
    click.secho(f'Successfully compiled binary {binary_name}', fg='green', err=True)

    return binary


def compile_c(workdir, files, target, verbose, options):
    compiler_args = [target.compiler] + target.flags
    if not target.asm64bit and any(f.suffix.lower() == '.s' for f in files):
        compiler_args.append('-m32')
    return compile_gnu(
            workdir,
            files,
            options,
            compiler_args,
            linker_args=[f'-l{lib}' for lib in target.libs],
            out_file=target.out,
            verbose=verbose
    )


def compile_cpp(workdir, files, options):
    return compile_gnu(workdir, files, options, GPP_ARGS)


def compile_gnu(workdir, files, options, compiler_args, linker_args=[], out_file='', verbose=False):
    filenames = [path.absolute() for path in files]

    command = compiler_args
    if options.asan:
        command += ASAN_ARGS
    if out_file:
        command += ['-o', (workdir / out_file).absolute()]
    command += filenames
    command += linker_args

    if verbose:
        click.secho('\nExecuting "{}"'.format(' '.join(map(str, command))))

    p = subprocess.run(command, cwd=workdir)

    if p.returncode != 0:
        return None

    return workdir / (out_file or 'a.out')


def run_solution(binary, args, options, test_data, capture_output=True):
    args = [binary.absolute()] + args

    env = os.environ
    if options.asan:
        env = dict(env, **ASAN_ENV)

    if options.valgrind:
        args = VALGRIND_ARGS + args

    if test_data.is_file():
        with test_data.input_file.open('rb') as f_in:
            process = subprocess.run(args, env=env, stdin=f_in, capture_output=capture_output)
    elif test_data.is_data():
        process = subprocess.run(args, env=env, input=test_data.input_data, capture_output=capture_output)
    elif test_data.is_stdin():
        process = subprocess.run(args, env=env, stdin=sys.stdin, capture_output=capture_output)
    else:
        raise Exception('Unknown test type')

    return process

