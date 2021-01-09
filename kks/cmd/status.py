import click

from kks.ejudge import ejudge_summary
from kks.util.common import get_valid_session, load_links


@click.command(short_help='Parse and display task status')
@click.argument('filters', nargs=-1)
def status(filters):
    """
    Parse and display task status

    If any FILTERS are specified, show status only for tasks with matching prefixes/names
    """

    session = get_valid_session()
    if session is None:
        return

    links = load_links()
    if links is None:
        click.secho('Auth data is invalid, use "kks auth" to authorize', fg='red', err=True)
        return

    problems = ejudge_summary(links, session)
    if filters:
        problems = [p for p in problems if any(p.short_name.startswith(f) for f in filters)]
        if not problems:
            click.secho('Nothing found')
            return

    row_format = "{:8} {:35} {:20} {:>5}"

    click.secho(row_format.format("Alias", "Name", "Status", "Score"), bold=True)

    for problem in problems:
        string = row_format\
            .format(problem.short_name, problem.name, problem.status, problem.score or '')

        click.secho(string, fg=problem.color(), bold=problem.bold())

    click.secho()
