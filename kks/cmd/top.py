import sys
from itertools import groupby

import click
from click._compat import isatty

from kks.ejudge import Status, ejudge_standings, get_group_id, get_contest_id, update_cached_problems, \
    PROBLEM_INFO_VERSION
from kks.util.fancytable import Column, StaticColumn, FancyTable
from kks.util.ejudge import EjudgeSession
from kks.util.stat import send_standings, get_global_standings
from kks.util.storage import Cache, Config

CONTEST_DELIMITER = ' | '


@click.command(short_help='Parse and display user standings')
@click.option('-l', '--last', type=int,
              help='Print result of last N contests')
@click.option('-a', '--all', 'all_', is_flag=True,
              help='Print result of all contests')
@click.option('-c', '--contest', 'contests', type=str, multiple=True,
              help='Print the results of the selected contest')
@click.option('-m', '--max', 'max_', is_flag=True,
              help='Print maximal possible scores (based on current deadlines)')
@click.option('-nc', '--no-cache', is_flag=True,
              help='Clear cache and reload task info (used with --max)')
@click.option('-g', '--global', 'global_', is_flag=True,
              help='Use global standings instead of group one. May be outdated')
@click.option('-f', '--group', 'groups', type=int, multiple=True,
              help='Print standings of selected groups')
@click.option('-r', '--recalculate', 'recalculate', is_flag=True,
              help='Calculate scores and sort based on filtered results')
@click.option('--global-opt-out', is_flag=True,
              help='Opt out from submitting your group results')
def top(last, all_, contests, groups, max_, no_cache, global_, recalculate, global_opt_out):
    """
    Parse and display user standings

    \b
    Example usage:
        kks top
        kks top --all
        kks top -c sm01 -c sm02
        kks top --last 2
    """

    config = Config()

    if global_opt_out:
        if click.confirm(click.style('Do you really want to opt out from sending your group standings to '
                                     'kks.darkkeks.me?', bold=True, fg='red')):
            opt_out(config)
        return
    elif config.options.global_opt_out is None:
        init_opt_out(config)

    session = EjudgeSession()
    standings = ejudge_standings(session)

    if not config.options.global_opt_out:
        if not send_standings(standings):
            click.secho('Failed to send standings to kks api', fg='yellow', err=True)

    if global_:
        standings = get_global_standings(standings.user)
        if standings is None:
            click.secho('Standings are not available now :(', fg='yellow', err=True)
            return

        if groups:
            standings = filter_groups(standings, groups)
            if standings is None:
                return

    if max_:
        standings = estimate_max(standings, session, no_cache)

    display_standings(standings, last, contests, all_, global_, recalculate)


def init_opt_out(config):
    click.secho('Standings can be sent for aggregation to kks api. '
                'This allows us to create global standings (you can try it out with kks top --global)', err=True)
    click.secho('You can always disable sending using kks top --global-opt-out', err=True)
    if click.confirm(click.style('Do you want to send group standings to kks api?', bold=True, fg='red'), default=True):
        click.secho('Thanks a lot for you contribution! We appreciate it!', fg='green', bold=True, err=True)
        config.options.global_opt_out = False
        config.save()
    else:
        opt_out(config)


def opt_out(config):
    click.secho('Successfully disabled standings sending. You can always enable sending by manually editing '
                '~/.kks/config.ini', color='red', err=True)
    config.options.global_opt_out = True
    config.save()


def display_standings(standings, last, contests, all_, global_, recalculate):
    table = FancyTable()

    table.add_column(StaticColumn('Place', 6, lambda row: row.place))
    table.add_column(StaticColumn.padding(1))
    table.add_column(StaticColumn('User', 24, lambda row: row.user, right_just=False))
    table.add_column(StaticColumn('Solved', 6, lambda row: row.solved))
    table.add_column(StaticColumn('Score', 6, lambda row: row.score))

    if global_:
        table.add_column(StaticColumn('Group', 6, lambda row: get_group_id(row.contest_id)))

    terminal_width = get_terminal_width()

    if isatty(sys.stdout):
        contests_width = terminal_width - table.calc_width() - 1
        default_contest_count = \
            get_default_contest_count(standings.contests, standings.tasks_by_contest, contests_width)
    else:
        default_contest_count = len(standings.contests)

    contests = select_contests(standings, last, contests, all_, default_contest_count)
    if contests is None:
        return

    if recalculate:
        recalculate_score(standings, contests)

    table.add_column(TasksColumn(contests, standings.tasks_by_contest))

    table.show(standings.rows, allow_high_tables=not global_)


def recalculate_score(standings, contests):
    for row in standings.rows:
        scores = [
            int(task.score)
            for task in row.tasks
            if task.contest in contests and task.score is not None and int(task.score) > 0
        ]
        row.score = sum(scores)
        # считаем количество решенных наивно
        # на самом деле в ejudge задача контрольной считается решенной, только если набрал полный балл
        row.solved = len(scores)

    sort_standings(standings)


class TasksColumn(Column):
    DELIMITER = ' | '

    def __init__(self, contests, tasks_by_contests):
        self.contests = contests
        self.contest_widths = get_contest_widths(self.contests, tasks_by_contests)

    def header(self):
        return ''.join([
            click.style(TasksColumn.DELIMITER, fg='white', bold=False) +
            click.style(contest.ljust(self.contest_widths[contest], ' '), fg='white', bold=True)
            for contest in self.contests
        ])

    def value(self, row):
        return ''.join([
            click.style(TasksColumn.DELIMITER, fg=row.color(), bold=row.bold()) + ' '.join([
                click.style('{:>3}'.format(task.table_score() or ''), fg=task.color(), bold=task.bold())
                for task in tasks
            ])
            for contest, tasks in groupby(row.tasks, lambda task: task.contest)
            if contest in self.contests
        ])

    def width(self):
        return sum(self.contest_widths.values()) + len(TasksColumn.DELIMITER) * len(self.contests)


def select_contests(standings, last, contests, all_, default_count):
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
                click.echo(
                    click.style('Contest ', fg='red') +
                    click.style(contest, fg='blue', bold=True) +
                    click.style(' not found!', fg='red'),
                    err=True
                )

        return [contest for contest in standings.contests if contest in contests]

    last = last or default_count

    return standings.contests[-last:] if last > 0 else []


def get_default_contest_count(contests, tasks_by_contest, max_width):
    """По ширине пытается определить, сколько колонок можно вывести"""

    delimiter_width = len(CONTEST_DELIMITER)
    contest_widths = get_contest_widths(contests, tasks_by_contest)

    width_sum = 0
    for i, contest in enumerate(contests[::-1]):
        width_sum += delimiter_width + contest_widths[contest]
        if width_sum > max_width:
            return i

    return len(contests)


def get_contest_widths(contests, tasks_by_contest):
    return {
        contest: len('100') * len(tasks_by_contest[contest]) + len(tasks_by_contest[contest]) - 1
        for contest in contests
    }


def get_terminal_width():
    (width, _) = click.get_terminal_size()
    return width


def filter_groups(standings, groups):
    group_contest_ids = []
    for group in groups:
        contest_id = get_contest_id(group)
        if contest_id is None:
            click.secho(f'Invalid group name: "{group}"', fg='red', err=True)
            return None
        group_contest_ids.append(contest_id)

    standings.rows = [
        row
        for row in standings.rows
        if row.contest_id in group_contest_ids
    ]

    for i, row in enumerate(standings.rows):
        row.place = i + 1

    return standings


def estimate_max(standings, session, force_reload):
    with Cache('problem_info', compress=True, version=PROBLEM_INFO_VERSION).load() as cache:
        if force_reload:
            cache.clear()

        names = [task.name for task in standings.tasks]
        problems = update_cached_problems(cache, names, session)

    for row in standings.rows:
        for task_score, problem_info in zip(row.tasks, problems):
            recalc_task_score(row, task_score, problem_info)

    sort_standings(standings)

    return standings


def recalc_task_score(row, task_score, problem_info):
    if problem_info.past_deadline() and task_score.status in [Status.NOT_SUBMITTED, Status.PARTIAL]:  # see #72
        return
    # NOTE may produce incorrect results for "kr" contests (with "max_kr" config option)
    # full score or run penalty for "kr" may be incorrect, scores may be partial
    is_testing_kr = task_score.contest.startswith('kr') and task_score.status == Status.TESTING
    if is_testing_kr and not Config().options.max_kr:
        return

    if task_score.score is None or task_score.score == '0':
        if task_score.status == Status.REJECTED:
            max_score = problem_info.full_score
        else:
            max_score = problem_info.full_score - problem_info.current_penalty
        if task_score.score == '0':  # at least one partial solution
            max_score -= problem_info.run_penalty
            # actually may be lower
        if is_testing_kr:
            max_score = 200  # not always true, but we cannot get real max_score
        if max_score > 0:
            row.solved += 1
            row.score += max_score
            task_score.score = str(max_score)
            task_score.status = Status.REVIEW


def sort_standings(standings):
    standings.rows.sort(key=lambda x: (x.score, -x.solved), reverse=True)
    for i, row in enumerate(standings.rows):
        row.place = i + 1
