from pathlib import Path

import click

from kks.ejudge_submit import submit_solution_api, submit_solution_ssh
from kks.util.common import prompt_choice, find_problem_rootdir, ssh_enabled, ssh_client
from kks.util.ejudge import EjudgeSession
from kks.errors import AuthError


API_TESTING_TIMEOUT = 10
SSH_TESTING_TIMEOUT = 20


def default_timeout(ctx, param, value):
    if value is not None:
        return value
    return SSH_TESTING_TIMEOUT if ssh_enabled() else API_TESTING_TIMEOUT


@click.command(short_help='Submit a solutions')
@click.argument('file', type=click.Path(exists=True), required=False)
@click.option('-p', '--problem', type=str,
              help='manually specify the problem ID')
@click.option('-t', '--timeout', type=float, callback=default_timeout,
              help=f'how long to wait for a testing report (default {API_TESTING_TIMEOUT}s / {SSH_TESTING_TIMEOUT}s with ssh)')
def submit(file, problem, timeout):
    """
    Submit a solution

    You should run this command from a synced directory or use -p option
    """

    if problem is None:
        rootdir = find_problem_rootdir()
        if rootdir is None:
            click.secho('Could not detect the problem id, use -p option', fg='red')
            return
        problem = get_problem_id(rootdir)

    if file is not None:
        file = Path(file)
    else:
        file = find_solution()
        if file is None:
            return

    if ssh_enabled():
        client = ssh_client()
        if client is None:
            return

        submit_solution = submit_solution_ssh
        connections = [client]  # may also need session in future
    else:
        try:
            session = EjudgeSession()
        except AuthError:
            return
        submit_solution = submit_solution_api
        connections = [session]

    result = submit_solution(file, problem, timeout, *connections)
    click.secho(result.msg, fg=result.color())


def get_problem_id(rootdir):
    return '{}-{}'.format(*rootdir.parts[-2:])


def find_solution():
    cwd = Path.cwd().resolve()
    source_files = list(cwd.glob('*.[chSs]'))
    if len(source_files) == 0:
        click.secho('No source files found', fg='red', err=True)
        return None
    if len(source_files) > 1:
        choices = [f.name for f in source_files]
        choices.append(click.style('Cancel', fg='red'))
        index = prompt_choice('Select a file to submit', choices)
        if index < len(source_files):
            return source_files[index]
        click.secho('Cancelled by user', fg='red')
        return None
    file = source_files[0]
    if click.confirm(f'Do you want to submit {file.name}?'):
        return file
    click.secho('Cancelled by user', fg='red')
    return None
