from pathlib import Path

import click

from kks.ejudge import ejudge_submit
from kks.util import get_valid_session, load_links, prompt_choice, find_workspace


def find_problem_rootdir():
    cwd = Path.cwd().resolve()
    workspace = find_workspace(cwd)
    if workspace is None:
        return None
    parts = cwd.relative_to(workspace).parts
    if len(parts) < 2:
        return None
    return workspace / parts[0] / parts[1]


def get_problem_id(rootdir):
    return '{}-{}'.format(*rootdir.parts[-2:])


def find_solution():
    cwd = Path.cwd().resolve()
    c_files = list(cwd.glob('*.c'))
    if len(c_files) == 0:
        click.secho('No .c files found', fg='red', err=True)
        return None
    if len(c_files) > 1:
        click.secho('Multiple .c files found, use one as an argument', fg='red', err=True)
        return None
    return c_files[0]


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

    def lang_choice(langs):
        choices = [e[0] for e in langs]
        lang_id = prompt_choice('Select a language / compiler', choices)
        return langs[lang_id]

    res, msg = ejudge_submit(links, session, file, problem, lang_choice)
    color = 'green' if res else 'red'
    click.secho(msg, fg=color)
