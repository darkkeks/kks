from datetime import datetime, timedelta

import click

from kks.ejudge import Deadlines, ProblemWithDeadline, Status, ejudge_summary, get_contest_deadlines
from kks.util.ejudge import EjudgeSession
from kks.util.fancytable import StaticColumn, DelimiterRow, FancyTable
from kks.util.storage import Config


class DeadlineColumn(StaticColumn):
    def __init__(self, name, right_just=True):
        super().__init__(name, len(Deadlines.PLACEHOLDER),
                         lambda problem: problem.deadline_string(),
                         right_just=right_just)

    def value(self, row):
        return click.style(self._justify(str(self.mapper(row))),
                           fg=row.deadline_color(), bold=row.deadline_is_close())


@click.command(short_help='Parse and display task status')
@click.option('-t', '--todo', is_flag=True,
              help='Show only unsolved problems')
@click.option('-nc', '--no-cache', is_flag=True,
              help='Reload cached data (if --todo is used)')
@click.argument('filters', nargs=-1)
def status(todo, no_cache, filters):
    """
    Parse and display task status

    If any FILTERS are specified, show status only for tasks with matching prefixes/names
    """

    session = EjudgeSession()
    problems = ejudge_summary(session)

    if todo:
        contest_info = get_contest_deadlines(session, problems, no_cache)
        contests = {contest.name: contest for contest in contest_info}
        submittable = [Status.NOT_SUBMITTED, Status.PARTIAL, Status.REJECTED]
        problems = [
            p for p in problems if p.status in submittable and not contests[p.contest()].past_deadline()
        ]
        if not problems:
            click.secho('All problems are solved', fg='green')
            return

        problems = [ProblemWithDeadline(p, contests[p.contest()]) for p in problems]
        if Config().options.sort_todo_by_deadline:
            far_future = datetime.now() + timedelta(days=365)
            problems.sort(key=lambda p: p.deadlines.soft or far_future)

    if filters:
        problems = [p for p in problems if any(p.short_name.startswith(f) for f in filters)]
        if not problems:
            click.secho('Nothing found')
            return

    table = FancyTable()
    table.add_column(StaticColumn('Alias', 6, lambda problem: problem.short_name, right_just=False))
    table.add_column(StaticColumn.padding(2))
    table.add_column(StaticColumn('Name', 35, lambda problem: problem.name, right_just=False))
    table.add_column(StaticColumn('Status', 20, lambda problem: problem.status, right_just=False))

    if todo:
        table.add_column(DeadlineColumn('Deadline', right_just=False))
    else:
        table.add_column(StaticColumn('Score', 5, lambda problem: problem.score or ''))

    rows = []
    for problem in problems:
        if rows and rows[-1].contest() != problem.contest():
            rows.append(DelimiterRow())
        rows.append(problem)
    table.show(rows)
