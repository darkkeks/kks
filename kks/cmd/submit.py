from pathlib import Path

import click

from kks.ejudge_submit import submit_solution
from kks.util.common import get_valid_session, load_links, prompt_choice, find_workspace, get_hidden_dir


@click.command(short_help='Submit a solutions')
@click.argument('file', type=click.Path(exists=True), required=False)
@click.option('-p', '--problem', type=str,
              help='manually specify the problem ID')
def submit(file, problem):
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

    session = get_valid_session()
    if session is None:
        return

    links = load_links()
    if links is None:
        click.secho('Auth data is invalid, use "kks auth" to authorize', fg='red', err=True)
        return

    res, msg = submit_solution(links, session, file, problem)
    color = 'green' if res else 'red'
    click.secho(msg, fg=color)


def find_problem_rootdir():
    cwd = Path.cwd().resolve()
    rootdir = find_workspace(cwd)
    if rootdir is None:
        return None
    hidden = get_hidden_dir(rootdir)
    if cwd.is_relative_to(hidden):
        rootdir = hidden
    parts = cwd.relative_to(rootdir).parts
    if len(parts) < 2:
        return None
    return rootdir / parts[0] / parts[1]


def get_problem_id(rootdir):
    return '{}-{}'.format(*rootdir.parts[-2:])


def find_solution():
    cwd = Path.cwd().resolve()
    source_files = list(cwd.glob('*.c')) + list(cwd.glob('*.h'))
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
