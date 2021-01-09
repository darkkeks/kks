import subprocess

from kks.util.common import run_script, test_number_to_name


class TestSource:
    def __init__(self, generator, solution, ignore_exit_code):
        self.generator = generator
        self.solution = solution
        self.ignore_exit_code = ignore_exit_code

    def generate_input(self, test, additional_args=None, stdout=subprocess.PIPE):
        args = [test] + (additional_args or [])
        return run_script(self.generator, args, stdout=stdout)

    def generate_output(self, test, additional_args=None, stdin=None, stdout=subprocess.PIPE, input=None):
        args = [test] + (additional_args or [])
        return run_script(self.solution, args, stdin=stdin, stdout=stdout, input=input)


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

    def __init__(self, name, test_type, input_file=None, output_file=None, input_data=None, output_data=None):
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
        return cls(name=name, test_type=Test.TYPE_FILE, input_file=input_file, output_file=output_file)

    @classmethod
    def from_data(cls, name, input_data, output_data):
        return cls(name=name, test_type=Test.TYPE_DATA, input_data=input_data, output_data=output_data)

    def read_input(self):
        if self.test_type == Test.TYPE_FILE:
            with self.output_file.open('rb') as f_in:
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
