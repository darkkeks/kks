import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import click

from kks.util.common import test_number_to_name
from kks.util.compat import subprocess
from kks.util.script import run_script, needs_compilation, compile_script


class TestSource:
    def __init__(self, generator, solution, options):
        self.generator = generator
        self.solution = solution
        self.options = options

        self.generator_directory = None
        if needs_compilation(self.generator):
            self.generator_directory = tempfile.TemporaryDirectory(prefix='kks-')

        self.solution_directory = None
        if needs_compilation(self.solution):
            self.solution_directory = tempfile.TemporaryDirectory(prefix='kks-')

    def generate_input(self, test, stdout=subprocess.PIPE):
        return run_script(self.generator, [test], stdout=stdout,
                          ignore_exit_code=self.options.ignore_exit_code)

    def generate_output(self, test, stdin=None, stdout=subprocess.PIPE, input=None):
        return run_script(self.solution, [test], stdin=stdin, stdout=stdout, input=input,
                          ignore_exit_code=self.options.ignore_exit_code)

    def __enter__(self):
        if self.generator_directory is not None:
            self.generator_directory.__enter__()
            path = Path(self.generator_directory.name)

            click.secho('Compiling generator... ', fg='green', err=True)
            self.generator = compile_script(path, self.generator, self.options)
            if self.generator is None:
                click.secho('Compilation failed!', fg='red', err=True)
                raise click.Abort()
            click.secho(f'Successfully compiled!', fg='green', err=True)

        if self.solution_directory is not None:
            self.solution_directory.__enter__()
            path = Path(self.solution_directory.name)

            click.secho('Compiling solution... ', fg='green', err=True)
            self.solution = compile_script(path, self.solution, self.options)
            if self.solution is None:
                click.secho('Compilation failed!', fg='red', err=True)
                raise click.Abort()
            click.secho(f'Successfully compiled!', fg='green', err=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.generator_directory is not None:
            self.generator_directory.__exit__(exc_type, exc_val, exc_tb)

        if self.solution_directory is not None:
            self.solution_directory.__exit__(exc_type, exc_val, exc_tb)


class VirtualTestSequence:
    def __init__(self, generator, tests):
        self.test_source = generator
        self.tests = tests

    def __iter__(self):
        for test in self.tests:
            name = test_number_to_name(test)
            input_data = self.test_source.generate_input(name).stdout
            output_data = self.test_source.generate_output(name, input=input_data).stdout
            yield DataTest(name, input_data, output_data)

    def __len__(self):
        return len(self.tests)


@dataclass(eq=False)
class Test(ABC):
    name: str

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        # NOTE not sure about this.
        # Should `kks run -f 001.dat -f tests/001.dat` run both tests?
        # If yes, subclasses should override __eq__ and filename should be added to WA output.
        if not isinstance(other, Test):
            return NotImplemented
        return self.name == other.name

    @abstractmethod
    def get_input(self):
        raise NotImplementedError()

    @abstractmethod
    def get_output(self):
        raise NotImplementedError()


@dataclass(eq=False)
class ManualTest(Test):
    name: str = 'stdin'

    def get_input(self):
        return None

    def get_output(self):
        return None


@dataclass(eq=False)
class FileTest(Test):
    input_file: Path
    output_file: Optional[Path]

    def get_input(self):
        with self.input_file.open('rb') as f_in:
            return f_in.read()

    def get_output(self):
        with self.output_file.open('rb') as f_out:
            return f_out.read()


@dataclass(eq=False)
class DataTest(Test):
    input_data: bytes
    output_data: bytes

    def get_input(self):
        return self.input_data

    def get_output(self):
        return self.output_data


class RunOptions:
    def __init__(self,
                 continue_on_error=False,
                 ignore_exit_code=False,
                 asan=True,
                 valgrind=False,
                 is_sample=False):
        self.continue_on_error = continue_on_error
        self.ignore_exit_code = ignore_exit_code
        self.asan = asan
        self.valgrind = valgrind
        self.is_sample = is_sample
