import os
import sys
from itertools import chain

import click

from kks.util.compat import subprocess
from kks.util.config import find_target
from kks.util.testing import DataTest, FileTest, ManualTest, Test


GPP_ARGS = [  # used only for test generator / solution
    'g++',
    '-std=gnu++17',
    '-g',
    '-O2',
    '-Werror',
    '-Wall',
    '-Wextra',
    '-ftrapv',
    '-pthread',
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
    '--quiet',
    '--leak-check=full',
    '--error-exitcode=1'
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

    has_c = any(f.name.endswith('.c') for f in source_files)
    has_cpp = any(f.name.endswith('.cpp') for f in source_files)
    # NOTE asm + cpp compilation was not tested
    if has_c and has_cpp:
        click.secho('Cannot compile C and C++ together', fg='red', err=True)
        return None

    click.secho('Compiling... ', fg='green', err=True, nl=False)

    binary = _compile_solution(directory, source_files, target, verbose, options, has_cpp)

    if binary is None:
        click.secho('Compilation failed!', fg='red', err=True)
        return None

    binary_name = click.style(binary.relative_to(directory).as_posix(), fg='red', bold=True)
    click.secho(f'Successfully compiled binary {binary_name}', fg='green', err=True)

    return binary


def _compile_solution(workdir, files, target, verbose, options, cpp):
    compiler = target.cpp_compiler if cpp else target.compiler
    std = target.cpp_std if cpp else target.std
    compiler_args = [compiler, '-std='+std] + target.flags

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


def compile_cpp(workdir, files, options, verbose=False):
    return compile_gnu(workdir, files, options, list(GPP_ARGS), verbose=verbose)


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


def run_solution(binary, args, options, test: Test, capture_output=True):
    args = [binary.absolute()] + args

    env = os.environ
    if options.asan:
        env = dict(env, **ASAN_ENV)

    if options.valgrind:
        args = VALGRIND_ARGS + args

    if isinstance(test, FileTest):
        with test.input_file.open('rb') as f_in:
            process = subprocess.run(
                args, env=env, stdin=f_in, capture_output=capture_output
            )
    elif isinstance(test, DataTest):
        process = subprocess.run(
            args, env=env, input=test.input_data, capture_output=capture_output
        )
    elif isinstance(test, ManualTest):
        process = subprocess.run(
            args, env=env, stdin=sys.stdin, capture_output=capture_output
        )
    else:
        raise Exception('Unknown test type')

    return process
