import click

from kks.ejudge import ejudge_summary
from kks.util import get_valid_session, load_links


@click.command()
def status():
    """Parse and display task status"""

    session = get_valid_session()
    if session is None:
        return

    links = load_links()
    if links is None:
        click.secho('Auth data is invalid, use "kks auth" to authorize', fg='red', err=True)
        return

    problems = ejudge_summary(links, session)

    row_format = "{:8} {:30} {:20} {:>5}"

    click.secho(row_format.format("Alias", "Name", "Status", "Score"), fg='green', bold=True)

    for problem in problems:
        string = row_format\
            .format(problem.short_name, problem.name, problem.status, problem.score or '')

        click.secho(string, fg=problem.color(), bold=problem.bold())

    click.secho()
