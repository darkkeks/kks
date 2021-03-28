from datetime import datetime, timedelta
from itertools import groupby

import click

from kks.ejudge import CacheKeys, ejudge_summary, update_cached_problems, PROBLEM_INFO_VERSION
from kks.util.fancytable import FancyTable, StaticColumn
from kks.util.ejudge import EjudgeSession
from kks.util.storage import Cache, Config


DATE_FORMAT = '%Y/%m/%d %H:%M:%S MSK'
DATE_PLACEHOLDER = '----/--/-- --:--:-- MSK'


class ContestStatusRow:
    def __init__(self, contest, problem):
        self.contest = contest
        self.penalty = 0
        self.status = 'No deadlines'
        self.deadline = ''
        self._color = 'green'
        self._bold = False

        if problem.past_deadline():
            self.status = 'Past deadline'
            self.penalty = '-'
            self._color = 'red'
        elif problem.deadlines.soft is not None:
            self.status = 'Next deadline'
            self.deadline = problem.deadlines.soft.strftime(DATE_FORMAT)
            dt = problem.deadlines.soft - datetime.now()
            warn = dt < timedelta(days=Config().options.deadline_warning_days)
            self.penalty = problem.current_penalty
            if warn:
                self.deadline += ' (!)'
            self._color = 'bright_yellow' if warn else 'yellow'
            self._bold = warn

    def color(self):
        return self._color

    def bold(self):
        return self._bold


@click.command(short_help='Show contest deadlines')
@click.option('-l', '--last', type=int,
              help='Show deadlines for last N contests')
@click.option('-c', '--contest', 'contests', type=str, multiple=True,
              help='Show deadlines for the selected contest')
@click.option('-nc', '--no-cache', is_flag=True,
              help='Reload cached data')
def deadlines(last, contests, no_cache):
    if last and contests:
        click.secho('"--last" and "--contest" are exclusive, specify no more than one')
        return

    session = EjudgeSession()
    summary = ejudge_summary(session)
    names = [problem.short_name for problem in summary]

    with Cache('problem_info', compress=True, version=PROBLEM_INFO_VERSION).load() as cache:

        if no_cache:
            for problem in summary:
                cache.erase(CacheKeys.deadline(problem.contest()))

        problems = update_cached_problems(cache, names, session, only_contests=True, summary=summary)

    contest_names = [contest for contest, _ in groupby(summary, lambda problem: problem.contest())]
    contest_info = list(zip(contest_names, problems))
    if contests:
        contest_info = [(c, p) for (c, p) in contest_info if c in contests]
    if last:
        contest_info = contest_info[-last:]

    rows = [ContestStatusRow(contest, problem) for contest, problem in contest_info]

    table = FancyTable()
    table.add_column(StaticColumn('Contest', 4, lambda row: row.contest))
    table.add_column(StaticColumn('Penalty', 3, lambda row: row.penalty))
    table.add_column(StaticColumn.padding(1))
    table.add_column(StaticColumn('Status', 13, lambda row: row.status, right_just=False))
    table.add_column(StaticColumn('Next deadline', len(DATE_PLACEHOLDER), lambda row: row.deadline, right_just=False))
    table.show(rows)
