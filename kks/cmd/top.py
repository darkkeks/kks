import click

from kks.ejudge import ejudge_standings
from kks.util import get_valid_session, load_links


@click.command()
@click.option('-a', '--all', '_all', is_flag=True,
              help='Print the whole table')
@click.option('-c', '--contest', type=str,
              help='Print the results of the selected contest')
def top(contest, _all):
    """
    Parse and display user standings

    \b
    Example usage:
        kks top     show only the last contest
        kks top -a
        kks top -c sm01
    """
    session = get_valid_session()
    if session is None:
        return

    links = load_links()
    if links is None:
        click.secho('Auth data is invalid, use "kks auth" to authorize', fg='red', err=True)
        return

    if _all:
        contest = '_all_'
    elif contest is None:
        contest = '_last_'

    task_map, standings = ejudge_standings(links, session)
    if task_map is None:
        click.secho('Standings are not available', fg='red', err=True)
        return
    if not task_map.contest_exists(contest):
        click.secho('This contest doesn\'t exist', fg='red', err=True)
        return

    row_format = "{:>6}  {:25} {:>7} {:>6}  {}"
    header = row_format.format("Place", "User", "Solved", "Score", "Tasks")

    click.secho(header, fg='white', bold=True)

    for row in standings:
        tasks = ' '.join([
            click.style('{:>3}'.format(task.score or ''), fg=task.color(), bold=task.bold())
            for task in task_map.filter(row.tasks, contest)
        ])
        string = row_format.format(row.place, row.user, row.solved, row.score, tasks)
        click.secho(string, fg=row.color(), bold=row.bold())


