import subprocess
from os import environ

import click
from tqdm import tqdm

from kks.binary import VALGRIND_ARGS

from kks.util import print_diff, format_file, test_number_to_name, run_script


class Generator:
    def __init__(self, generator, solution):
        self.generator = generator
        self.solution = solution

    def generate_tests(self, test_pairs, output_only, force, gen_args):
        generated_tests = 0
        t = tqdm(test_pairs, leave=False)
        for input_file, output_file in t:
            if not output_only and input_file.exists() and not force:
                t.clear()
                click.secho(f'Input file {format_file(input_file)} '
                            'already exists, skipping. Specify -f to overwrite', fg='yellow', err=True)
                continue

            if output_only and not input_file.exists():
                t.clear()
                click.secho(f'Input file {format_file(input_file)} '
                            'does not exist, skipping', fg='red', err=True)
                continue

            if output_file and output_file.exists() and not force:
                t.clear()
                click.secho(f'Output file {format_file(output_file)} '
                            'already exists, skipping. Specify -f to overwrite', fg='yellow', err=True)
                continue

            t.set_description(f'Generating test {format_file(input_file)}')

            if not output_only:
                with input_file.open('wb') as f:
                    args = [input_file.stem] + list(gen_args)
                    if run_script(self.generator, args, stdout=f) is None:
                        return

            with input_file.open('rb') as f_in, output_file.open('wb') as f_out:
                args = [input_file.stem]
                if run_script(self.solution, args, stdin=f_in, stdout=f_out) is None:
                    return

            generated_tests += 1

        click.secho(f'Generated {generated_tests} tests!', fg='green')

    def gen_input(self, test):
        # gen_args are not supported
        args = [test_number_to_name(test)]
        proc = run_script(self.generator, args, stdout=subprocess.PIPE)
        if proc is None:
            return None
        return proc.stdout

    def gen_output(self, test, input_data):
        args = [test_number_to_name(test)]
        proc = run_script(self.solution, args, stdin=None, stdout=subprocess.PIPE, input=input_data)
        if proc is None:
            return None
        return proc.stdout


class VirtTestSequence:
    def __init__(self, generator, tests):
        self.generator = generator
        self.tests = tests

    def __iter__(self):
        for test in self.tests:
            input_data = self.generator.gen_input(test)
            yield str(test), input_data, self.generator.gen_output(test, input_data)

    def __len__(self):
        return len(self.tests)


class Checker:
    def __init__(self, continue_on_error, valgrind):
        self.cont = continue_on_error
        self.valgrind = valgrind

    def run_tests(self, binary, tests, is_sample):
        self._run_tests(binary, tests, False, is_sample)

    def run_virtual(self, binary, generator, tests):
        self._run_tests(binary, VirtTestSequence(generator, tests), True)

    def _run_tests(self, binary, test_seq, virtual, is_sample=False):
        successful_count = 0
        ran_count = 0

        test_env = dict(environ, ASAN_OPTIONS="color=always")
        t = tqdm(test_seq, leave=False)
        for test_data in t:
            if not virtual:
                in_, out = test_data
                test = in_
            else:
                test, in_, out = test_data

            if not virtual and is_sample:
                t.clear()
                with in_.open('r') as f:  # text mode is OK for sample
                    input_data = f.read()
                click.secho("Sample input:", bold=True)
                click.secho(input_data)
                with out.open('r') as f:
                    output_data = f.read()
                click.secho("Sample output:", bold=True)
                click.secho(output_data)

            t.set_description(f'Running {format_file(test)}')

            test_number = test if virtual else test.stem
            is_success = self._run_test(binary, test_number, in_, out, virtual, test_env)

            ran_count += 1
            successful_count += is_success

            if not self.cont and not is_success:
                t.close()
                break

        color = 'red' if ran_count != successful_count else 'green'
        click.secho(f'Tests passed: {successful_count}/{ran_count}', fg=color, bold=True)

    def _run_test(self, binary, test_number, in_, out, virtual, env):
        args = [binary.absolute()]
        if self.valgrind:
            args = VALGRIND_ARGS + args
        if virtual:
            process = subprocess.run(args, input=in_, capture_output=True, env=env)
        else:
            with in_.open('rb') as input_f:
                process = subprocess.run(args, stdin=input_f, capture_output=True, env=env)

        if process.returncode != 0:
            error_output = process.stderr.decode('utf-8')
            click.secho(f'RE {test_number}', fg='red', bold=True)
            click.secho(f'Process exited with code {process.returncode}', fg='red')
            if error_output:
                click.secho(error_output)
            return False

        if virtual:
            expected_output = out
        else:
            with out.open('rb') as output_f:
                expected_output = output_f.read()

        actual_output = process.stdout

        if expected_output != actual_output:
            click.secho(f'WA {test_number}', fg='red', bold=True)
            try:
                expected = expected_output.decode('utf-8')
                actual = actual_output.decode('utf-8')
                print_diff(expected, actual, 'expected', 'actual')
                click.secho()
            except UnicodeDecodeError:
                click.secho('Output differs, but cant be decoded as utf-8', fg='red')
            return False

        return True
