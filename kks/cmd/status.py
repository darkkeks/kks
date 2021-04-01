import click

from kks.ejudge import Status, ejudge_summary, get_contest_deadlines
from kks.util.ejudge import EjudgeSession
from kks.util.fancytable import StaticColumn, DelimiterRow, FancyTable


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
        problems = [p for p in problems if p.status in [Status.NOT_SUBMITTED, Status.PARTIAL, Status.REJECTED] and not contests[p.contest()].past_deadline()]

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
    table.add_column(StaticColumn('Score', 5, lambda problem: problem.score or ''))
    rows = []
    for problem in problems:
        if rows and rows[-1].contest() != problem.contest():
            rows.append(DelimiterRow())
        rows.append(problem)
    table.show(rows)
