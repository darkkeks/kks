import click

from kks.ejudge import ejudge_standings
from kks.util import get_valid_session, load_links


@click.command()
def top():
    """Parse and display user standings"""

    session = get_valid_session()
    if session is None:
        return

    links = load_links()
    if links is None:
        click.secho('Auth data is invalid, use "kks auth" to authorize', fg='red', err=True)
        return

    standings = ejudge_standings(links, session)

    row_format = "{:>6}  {:25} {:>7} {:>6}  {}"

    click.secho(row_format.format("Place", "User", "Solved", "Score", "Tasks"), fg='white', bold=True)

    for row in standings:
        tasks = ' '.join([
            click.style('{:>3}'.format(task.score or ''), fg=task.color(), bold=task.bold())
            for task in row.tasks
        ])

        string = row_format.format(row.place, row.user, row.solved, row.score, tasks)
        click.secho(string, fg=row.color(), bold=row.bold())


