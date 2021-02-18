import os
import sys
from collections import namedtuple
from itertools import groupby

import click
from click._compat import isatty, strip_ansi
from tqdm import tqdm

from kks.ejudge import Status, ejudge_standings, ejudge_summary, get_problem_info, extract_contest_name, get_group_id
from kks.util.ejudge import EjudgeSession
from kks.util.stat import send_standings, get_global_standings
from kks.util.storage import Cache, Config

Problem = namedtuple('Problem', ['href', 'short_name', 'contest'])  # used for caching the problem list

CONTEST_DELIMITER = ' | '


@click.command(short_help='Parse and display user standings')
@click.option('-l', '--last', type=int,
              help='Print result of last N contest')
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
@click.option('--global-opt-out', is_flag=True,
              help='Opt out from submitting your group results')
def top(last, contests, all_, max_, no_cache, global_, global_opt_out):
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
        standings = get_global_standings()
        if standings is None:
            click.secho('Standings are not available now :(', fg='yellow', err=True)
            return

    if max_:
        standings = estimate_max(standings, session, no_cache)

    display_standings(standings, last, contests, all_, global_)


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


def display_standings(standings, last, contests, all_, global_):
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

    table.add_column(TasksColumn(contests, standings.tasks_by_contest))

    exceeds_width = table.calc_width() > terminal_width

    lines = table.render(standings.rows)
    output = '\n'.join(lines)

    if isatty(sys.stdout) and (exceeds_width or global_):
        if 'LESS' not in os.environ:
            os.environ['LESS'] = '-S -R'
        click.echo_via_pager(output)
    else:
        click.secho(output)


class Column:
    def header(self):
        raise NotImplemented()

    def value(self, row):
        raise NotImplemented()

    def width(self):
        raise NotImplemented()


class StaticColumn(Column):
    def __init__(self, name, width, mapper, right_just=True):
        self.name = name
        if self.name is None:
            self.name = ''
        self.mapper = mapper
        self.actual_width = max(width, len(self.name))
        self.right_just = right_just

    def _justify(self, value):
        return value.rjust(self.actual_width, ' ') if self.right_just \
            else value.ljust(self.actual_width, ' ')

    def header(self):
        return click.style(self._justify(self.name), fg='white', bold=True)

    def value(self, row):
        return click.style(self._justify(str(self.mapper(row))), fg=row.color(), bold=row.bold())

    def width(self):
        return self.actual_width

    @classmethod
    def padding(cls, width):
        # width - 1, так как лишняя колонка уже добавляет один пробел
        return cls(None, width - 1, lambda _: '')


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


class FancyTable:
    def __init__(self):
        self.columns = []

    def add_column(self, column):
        self.columns.append(column)

    def calc_width(self):
        content = sum([column.width() for column in self.columns])
        return content + len(self.columns) - 1

    def render(self, rows):
        lines = [
            ' '.join([
                column.header()
                for column in self.columns
            ])
        ]

        for row in rows:
            lines.append(' '.join([
                column.value(row)
                for column in self.columns
            ]))

        return lines


def select_contests(standings, last, contests, all_, default_count):
    has_last = last is not None
    has_contests = len(contests) > 0

    if sum([has_last, has_contests, all_]) > 1:
        click.secho('Arguments are exclusive, specify no more than one')
        return None

    if all_:
        return standings.contests

    if has_contests:
        def is_available(contest):
            if contest not in standings.contests:
                click.echo(
                    click.style('Contest ', fg='red') +
                    click.style(contest, fg='blue', bold=True) +
                    click.style(' not found!', fg='red'),
                    err=True
                )
            return contest in standings.contests

        return list(filter(is_available, contests))

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


def estimate_max(standings, session, force_reload):
    # NOTE may produce incorrect results for "krxx" contests (they may be reopened?)

    def cached_problem(problem):
        return Problem(problem.href, problem.short_name, extract_contest_name(problem.short_name))

    standings.rows = list(standings.rows)

    with Cache('problem_info', compress=True).load() as cache:
        if force_reload:
            cache.clear()

        problem_list = cache.get('problem_links', [])  # we can avoid loading summary

        with tqdm(total=len(standings.tasks), leave=False) as pbar:
            def with_progress(func, *args, **kwargs):
                result = func(*args, **kwargs)
                pbar.update(1)
                return result

            if len(problem_list) != len(standings.tasks) or \
                    any(problem.short_name != task.name for problem, task in zip(problem_list, standings.tasks)):
                problem_list = ejudge_summary(session)
                problem_list = [cached_problem(p) for p in problem_list]
                cache.set('problem_links', problem_list)
            problems = [with_progress(get_problem_info, problem, cache, session) for problem in problem_list]

    for row in standings.rows:
        for task_score, problem in zip(row.tasks, problems):
            if task_score.score is None or task_score.score == '0':
                if task_score.status == Status.REJECTED:
                    max_score = problem.full_score
                else:
                    max_score = problem.full_score - problem.current_penalty
                    if task_score.score == '0':
                        max_score -= problem.run_penalty
                        # actually may be lower
                if max_score > 0:
                    row.solved += 1
                    row.score += max_score
                    task_score.score = max_score
                    task_score.status = Status.REVIEW

    standings.rows.sort(key=lambda x: (x.score, x.solved), reverse=True)
    for i, row in enumerate(standings.rows):
        row.place = i + 1

    return standings
