import tempfile
from pathlib import Path

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
            yield Test.from_data(name, input_data, output_data)

    def __len__(self):
        return len(self.tests)


class Test:
    TYPE_STDIN = 'stdin'
    TYPE_FILE = 'file'
    TYPE_DATA = 'data'

    def __init__(  # TODO use dataclass?
        self,
        name, test_type,
        input_file=None, output_file=None,
        input_data=None, output_data=None
    ):
        self.name = name
        self.test_type = test_type
        self.input_file = input_file
        self.output_file = output_file
        self.input_data = input_data
        self.output_data = output_data

    @classmethod
    def from_stdin(cls):
        return cls(name='stdin', test_type=Test.TYPE_STDIN)

    @classmethod
    def from_file(cls, name, input_file, output_file):
        return cls(
            name=name, test_type=Test.TYPE_FILE, input_file=input_file, output_file=output_file
        )

    @classmethod
    def from_data(cls, name, input_data, output_data):
        return cls(
            name=name, test_type=Test.TYPE_DATA, input_data=input_data, output_data=output_data
        )

    def is_file(self):
        return self.test_type == Test.TYPE_FILE

    def is_data(self):
        return self.test_type == Test.TYPE_DATA

    def is_stdin(self):
        return self.test_type == Test.TYPE_STDIN

    def read_input(self):
        if self.test_type == Test.TYPE_FILE:
            with self.input_file.open('rb') as f_in:
                return f_in.read()
        elif self.test_type == Test.TYPE_DATA:
            return self.input_data
        else:
            return None

    def read_output(self):
        if self.test_type == Test.TYPE_FILE:
            with self.output_file.open('rb') as f_out:
                return f_out.read()
        elif self.test_type == Test.TYPE_DATA:
            return self.output_data
        else:
            return None


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
