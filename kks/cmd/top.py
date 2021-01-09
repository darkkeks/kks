from itertools import groupby

import click

from kks.ejudge import ejudge_standings
from kks.util.common import get_valid_session, load_links

ROW_FORMAT = "{:>6}  {:25} {:>7} {:>6}{}"
PREFIX_LENGTH = sum([6, 2, 25, 1, 7, 1, 6])
CONTEST_DELIMITER = ' | '


@click.command(short_help='Parse and display user standings')
@click.option('-l', '--last', type=int,
              help='Print result of last N contest')
@click.option('-a', '--all', 'all_', is_flag=True, default=False,
              help='Print result of all contests')
@click.option('-c', '--contest', 'contests', type=str, multiple=True,
              help='Print the results of the selected contest')
def top(last, contests, all_):
    """
    Parse and display user standings

    \b
    Example usage:
        kks top
        kks top --all
        kks top -c sm01 -c sm02
        kks top --last 2
    """
    session = get_valid_session()
    if session is None:
        return

    links = load_links()
    if links is None:
        click.secho('Auth data is invalid, use "kks auth" to authorize', fg='red', err=True)
        return

    standings = ejudge_standings(links, session)
    contests = select_contests(standings, last, contests, all_)
    if contests is None:
        return

    contest_widths = get_contest_widths(standings.contests, standings.tasks_by_contest)
    contests_header = ''.join([
        CONTEST_DELIMITER + contest.ljust(contest_widths[contest], ' ')
        for contest in contests
    ])
    header = ROW_FORMAT.format("Place", "User", "Solved", "Score", contests_header)

    click.secho(header, fg='white', bold=True)

    for row in standings.rows:
        tasks = ''.join([
            click.style(CONTEST_DELIMITER, fg=row.color(), bold=row.bold()) + ' '.join([
                click.style('{:>3}'.format(task.score or ''), fg=task.color(), bold=task.bold())
                for task in tasks
            ])
            for contest, tasks in groupby(row.tasks, lambda task: task.contest)
            if contest in contests
        ])

        string = ROW_FORMAT.format(row.place, row.user, row.solved, row.score, tasks)
        click.secho(string, fg=row.color(), bold=row.bold())


def select_contests(standings, last, contests, all_):
    has_last = last is not None
    has_contests = len(contests) > 0

    if sum([has_last, has_contests, all_]) > 1:
        click.secho('Arguments are exclusive, specify no more than one')
        return None

    if all_:
        return standings.contests

    if has_contests:
        for contest in contests:
            if contest not in standings.contests:
                click.secho('Contest ' + click.style(contest, fg='blue', bold=True) + ' not found!', fg='red', err=True)
                return None
        return contests

    last = last or get_default_contest_count(standings.contests, standings.tasks_by_contest)

    return standings.contests[-last:] if last > 0 else []


def get_default_contest_count(contests, tasks_by_contest):
    """По ширине терминала пытается определить, сколько колонок можно вывести"""
    (width, _) = click.get_terminal_size()

    delimiter_width = len(CONTEST_DELIMITER)
    contest_widths = get_contest_widths(contests, tasks_by_contest)

    width_sum = 0
    for i, contest in enumerate(contests[::-1]):
        width_sum += delimiter_width + contest_widths[contest]
        if width_sum + PREFIX_LENGTH > width:
            return i

    return len(contests)


def get_contest_widths(contests, tasks_by_contest):
    return {
        contest: len('100') * len(tasks_by_contest[contest]) + len(tasks_by_contest[contest]) - 1
        for contest in contests
    }
