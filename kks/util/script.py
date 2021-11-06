from pathlib import Path

import click

from kks.binary import compile_cpp
from kks.util.common import format_file
from kks.util.compat import subprocess


# Используются для поиска скриптов по имени
SCRIPT_EXTENSIONS = ['.py', '.py3', '.sh', '.out', '.cpp']

# Перед вызовом run_script .cpp скрипты будут скомпилированы в временной папке
CPP_EXTENSIONS = ['.cpp']


def run_script(script, args, ignore_exit_code=False, stdin=None, stdout=None, input=None):
    ext = script.suffix

    interpreter = ['python3'] if ext in ['.py', '.py3'] \
        else ['bash'] if ext in ['.sh'] \
        else [] if ext in ['.out', ''] \
        else None

    if interpreter is None:
        click.secho(f'Cant run unrecognized script {format_file(script)}', fg='red', err=True)
        return None

    process = subprocess.run(
        interpreter + [script.absolute()] + args, stdin=stdin, stdout=stdout, input=input
    )

    if process.returncode != 0 and not ignore_exit_code:
        click.secho('Script exited with code ' +
                    click.style(str(process.returncode), fg='red', bold=True) +
                    ' (args: ' + ' '.join(args) + ')', fg='yellow')
        return None

    return process


def needs_compilation(script):
    return script is not None and script.suffix in CPP_EXTENSIONS


def compile_script(workdir, script, options):
    if script.suffix in CPP_EXTENSIONS:
        return compile_cpp(workdir, [script], options)
    else:
        raise Exception(f'Cant compile script with extension {script.suffix}')


def find_script(search_directory, name, default=None, exists=True):
    result = Path(default) if default is not None else None
    if result is None:
        files = search_directory.glob(f'{name}.*')
        for file in files:
            if file.suffix in SCRIPT_EXTENSIONS:
                result = Path(file)
                click.secho(f'Using script {format_file(result)}', err=True)
                break
        if result is None and exists:
            click.secho(f'Can\'t find any script with name "{name}"', fg='red', err=True)
            return None

    if not result.exists() and exists:
        click.secho(f'Script {result} does not exist', fg='red', err=True)
        return None

    return result
