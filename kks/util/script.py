import atexit
import contextlib
import multiprocessing
from contextlib import redirect_stdout
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple, Union

import click

from kks.util.common import format_file, override_attr
from kks.util.compat import subprocess


FileArgs = Tuple[Path, str]
StreamArgs = Union[FileArgs, Literal[subprocess.PIPE]]


# Используются для поиска скриптов по имени
SCRIPT_EXTENSIONS = ['.py', '.py3', '.sh', '.out', '.cpp']

# Перед вызовом run_script .cpp скрипты будут скомпилированы в временной папке
CPP_EXTENSIONS = ['.cpp']


@dataclass
class RunResult:
    ok: bool
    output: Optional[bytes] = None
    retcode: int = 0


class redirect_stdin(contextlib._RedirectStream):
    _stream = "stdin"


class Runner:
    _has_atexit = False
    _rerun_flag = '_rerun_'
    _known_scripts = set()
    _runners: Dict[Path, 'Runner'] = {}

    def __init__(self, script):
        self.script = script
        self._conn, conn2 = multiprocessing.Pipe()
        self._proc = multiprocessing.Process(target=self._exec_loop, args=(conn2,))
        self._proc.start()
        conn2.close()

    def execute(
        self,
        args: List[str],
        ignore_exit_code=False,
        stdin: Optional[FileArgs] = None,
        stdout: Optional[StreamArgs] = None,
        input: Optional[bytes] = None
    ) -> RunResult:
        # TODO handle errors
        self._conn.send((args, ignore_exit_code, stdin, stdout, input))
        return self._conn.recv()

    def _exec_loop(self, conn):
        import os
        import sys
        import traceback
        from io import BytesIO, TextIOWrapper

        def make_buffered(stream):
            if hasattr(stream, 'buffer'):
                return stream
            return TextIOWrapper(stream)

        def weak_exit(code):
            raise SystemExit(code)

        self._conn.close()
        self._conn = conn
        loader = self._loader(self.script)
        spec = spec_from_loader(loader.name, loader)
        module = module_from_spec(spec)
        script_name = self.script.as_posix()
        while True:
            # TODO handle errors
            args, ignore_exit_code, stdin, stdout, input = self._conn.recv()
            out_stream = None
            with open_streams(stdin, stdout) as (stdin, stdout), \
                    override_attr(os, '_exit', weak_exit), \
                    override_attr(sys, 'argv', [script_name] + args):
                with contextlib.ExitStack() as stack:
                    if stdin is not None:
                        stack.enter_context(redirect_stdin(make_buffered(stdin)))
                    else:
                        stack.enter_context(redirect_stdin(TextIOWrapper(BytesIO(input))))
                    if stdout is not None:
                        if stdout == subprocess.PIPE:
                            out_stream = stack.enter_context(
                                redirect_stdout(TextIOWrapper(BytesIO()))
                            )
                        else:
                            stack.enter_context(redirect_stdout(make_buffered(stdout)))
                    try:
                        loader.exec_module(module)
                        retcode = 0
                    except Exception as e:
                        print(traceback.format_exc(), file=sys.stderr)
                        sys.stderr.flush()
                        retcode = 1
                    except SystemExit as e:
                        retcode = e.args[0]
                    finally:
                        sys.stdout.flush()
            if out_stream is None:
                output = None
            else:
                output = out_stream.buffer.getvalue()
            self._conn.send(RunResult(retcode == 0, output, retcode))

    @staticmethod
    def _loader(script: Path) -> SourceFileLoader:
        return SourceFileLoader('__main__', script.as_posix())

    @staticmethod
    def _flag_is_true(code, name):
        import dis
        sentinel = (..., None, ...)
        last_const = sentinel
        for insn in dis.get_instructions(code):
            if insn.opname == 'LOAD_CONST':
                last_const = insn.argval
            elif insn.opname == 'STORE_NAME' and insn.argval == Runner._rerun_flag:
                if last_const == sentinel:
                    return False  # Something more complex. Disable rerun just in case
                # NOTE reassignments are ignored, only the first value is returned
                return bool(last_const)
            else:
                last_const = sentinel
        return False  # couldn't find STORE_VALUE?

    @classmethod
    def _stop_all(cls):
        # parallel stop
        for runner in cls._runners.values():
            runner._proc.terminate()
        for runner in cls._runners.values():
            runner._proc.join()
        # explicitly close connections?
        cls._runners.clear()

    @classmethod
    def get(cls, script: Path) -> Optional['Runner']:
        orig_script = script
        script = script.resolve()
        if script in cls._known_scripts:
            return cls._runners.get(script)
        cls._known_scripts.add(script)
        loader = cls._loader(script)
        code = loader.get_code(loader.name)
        if cls._rerun_flag not in code.co_names:
            return None
        if not cls._flag_is_true(code, cls._rerun_flag):
            return None
        if not cls._has_atexit:
            atexit.register(cls._stop_all)
            cls._has_atexit = True
        click.secho('Using optimizations for ' + format_file(orig_script), fg='green')
        cls._runners[script] = Runner(script)
        return cls._runners[script]


@contextlib.contextmanager
def open_streams(*stream_args: Optional[StreamArgs]):
    """Multi-open context manager"""
    streams = []
    # if open() raoses an exception, all previously opened files will be closed
    with contextlib.ExitStack() as stack:
        for args in stream_args:
            if args is None or args == subprocess.PIPE:
                streams.append(args)
                continue
            f, mode = args
            streams.append(stack.enter_context(f.open(mode)))
        close_streams = stack.pop_all()
    try:
        yield streams
    finally:
        close_streams.close()


def log_failure(script: Path, retcode: int, args: List[str]):
    click.echo(
        click.style('Script ', fg='yellow') +
        format_file(script.name) +
        click.style(' exited with code ', fg='yellow') +
        click.style(str(retcode), fg='red', bold=True) +
        click.style(' (args: ' + ' '.join(args) + ')', fg='yellow')
    )


def run_script(
    script: Path,
    args: List[str],
    ignore_exit_code=False,
    stdin: Optional[FileArgs] = None,  # No sense in using PIPE
    stdout: Optional[StreamArgs] = None,  # None is never used?
    input: Optional[bytes] = None
) -> RunResult:
    ext = script.suffix

    interpreter = ['python3'] if ext in ['.py', '.py3'] \
        else ['bash'] if ext in ['.sh'] \
        else [] if ext in ['.out', ''] \
        else None

    if interpreter is None:
        click.secho(f'Cant run unrecognized script {format_file(script)}', fg='red', err=True)
        return RunResult(False)

    if interpreter == ['python3']:
        runner = Runner.get(script)
        if runner is not None:
            result = runner.execute(args, ignore_exit_code, stdin, stdout, input)
            if result.retcode != 0:
                log_failure(script, result.retcode, args)
            return result

    with open_streams(stdin, stdout) as (stdin, stdout):
        process = subprocess.run(
            interpreter + [script.absolute()] + args, stdin=stdin, stdout=stdout, input=input
        )

    if process.returncode != 0 and not ignore_exit_code:
        log_failure(script, process.returncode, args)
        return RunResult(False, retcode=process.returncode)

    if stdout == subprocess.PIPE:
        return RunResult(True, process.stdout)
    return RunResult(True)


def needs_compilation(script):
    return script is not None and script.suffix in CPP_EXTENSIONS


def compile_script(workdir, script, options):
    from kks.binary import compile_cpp  # avoid circular import. TODO refactor kks.binary?
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
