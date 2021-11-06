from itertools import groupby

import click

from kks.ejudge import Deadlines, Status, ejudge_summary, get_contest_deadlines
from kks.util.fancytable import FancyTable, StaticColumn
from kks.util.ejudge import EjudgeSession


class ContestStatusRow:
    def __init__(self, contest, problem_mapping):
        self.contest = contest.name
        self.penalty = contest.current_penalty
        self.status = 'No deadlines'
        self.deadline = ''
        self._color = contest.deadline_color()
        self._bold = False

        if contest.past_deadline():
            self.status = 'Past deadline'
            self.penalty = '-'
        elif contest.active_deadline() is not None:
            self.status = 'Next deadline'
            self.deadline = contest.deadlines.to_str(contest.active_deadline())
            warn = contest.deadline_is_close()
            self._bold = warn
        if (
            not contest.past_deadline()
            and all(
                problem.status in [Status.OK, Status.OK_AUTO, Status.REVIEW]
                for problem in problem_mapping[contest.name]
            )
        ):
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
@click.option('-C', '-nc', '--no-cache', is_flag=True,
              help='Reload cached data')
def deadlines(last, contests, no_cache):
    if last and contests:
        click.secho('"--last" and "--contest" are exclusive, specify no more than one')
        return

    session = EjudgeSession()
    summary = ejudge_summary(session)
    problem_mapping = {
        contest: list(problems)
        for contest, problems in groupby(summary, lambda problem: problem.contest())
    }
    contest_info = get_contest_deadlines(session, summary, no_cache)

    if contests:
        contest_info = [contest for contest in contest_info if contest.name in contests]
    if last:
        contest_info = contest_info[-last:]

    rows = [ContestStatusRow(contest, problem_mapping) for contest in contest_info]

    table = FancyTable()
    table.add_column(StaticColumn('Contest', 4, lambda row: row.contest))
    table.add_column(StaticColumn('Penalty', 3, lambda row: row.penalty))
    table.add_column(StaticColumn.padding(1))
    table.add_column(StaticColumn('Status', 13, lambda row: row.status, right_just=False))
    table.add_column(StaticColumn('Next deadline', len(Deadlines.PLACEHOLDER),
                                  lambda row: row.deadline, right_just=False))
    table.show(rows)
