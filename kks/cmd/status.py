import click

from kks.ejudge import ejudge_summary, Status
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

    row_format = "{:8} {:30} {:20} {:5}"

    click.secho(row_format.format("Alias", "Name", "Status", "Score"), fg='green', bold=True)

    for problem in problems:
        color = 'green' if problem.status == Status.OK \
            else 'yellow' if problem.status == Status.REVIEW \
            else 'white' if problem.status == Status.NOT_SUBMITTED \
            else 'red'

        string = row_format\
            .format(problem.short_name, problem.name, problem.status, problem.score)

        click.secho(string, fg=color)

    click.secho()
