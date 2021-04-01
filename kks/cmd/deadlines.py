from datetime import datetime, timedelta
from itertools import groupby

import click

from kks.ejudge import Status, get_contest_deadlines, ejudge_summary
from kks.util.fancytable import FancyTable, StaticColumn
from kks.util.ejudge import EjudgeSession
from kks.util.storage import Cache, Config


DATE_FORMAT = '%Y/%m/%d %H:%M:%S MSK'
DATE_PLACEHOLDER = '----/--/-- --:--:-- MSK'


class ContestStatusRow:
    def __init__(self, contest, problem_mapping):
        self.contest = contest.name
        self.penalty = 0
        self.status = 'No deadlines'
        self.deadline = ''
        self._color = 'green'
        self._bold = False

        if contest.past_deadline():
            self.status = 'Past deadline'
            self.penalty = '-'
            self._color = 'red'
        elif contest.deadlines.soft is not None:
            self.status = 'Next deadline'
            self.deadline = contest.deadlines.soft.strftime(DATE_FORMAT)
            dt = contest.deadlines.soft - datetime.now()
            warn = dt < timedelta(days=Config().options.deadline_warning_days)
            self.penalty = contest.current_penalty
            if warn:
                self.deadline += ' (!)'
            self._color = 'bright_yellow' if warn else 'yellow'
            self._bold = warn
        if not contest.past_deadline() and all(problem.status in [Status.OK, Status.OK_AUTO, Status.REVIEW] for problem in problem_mapping[contest.name]):
            self._color = 'bright_black'

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
    contest_info = get_contest_deadlines(session, summary, no_cache)
    # FIXME grouping is done 3 times - in get_contest_deadlines -> in update_cached_problems and herr. Try to refactor / optimize it
    problem_mapping = {contest: list(problems) for contest, problems in groupby(summary, lambda problem: problem.contest())}

    if contests:
        contest_info = [(c, p) for (c, p) in contest_info if c in contests]
    if last:
        contest_info = contest_info[-last:]

    rows = [ContestStatusRow(contest, problem_mapping) for contest in contest_info]

    table = FancyTable()
    table.add_column(StaticColumn('Contest', 4, lambda row: row.contest))
    table.add_column(StaticColumn('Penalty', 3, lambda row: row.penalty))
    table.add_column(StaticColumn.padding(1))
    table.add_column(StaticColumn('Status', 13, lambda row: row.status, right_just=False))
    table.add_column(StaticColumn('Next deadline', len(DATE_PLACEHOLDER), lambda row: row.deadline, right_just=False))
    table.show(rows)
