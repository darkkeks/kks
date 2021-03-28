import click

from kks.ejudge import ejudge_summary
from kks.util.ejudge import EjudgeSession
from kks.util.fancytable import StaticColumn, FancyTable


@click.command(short_help='Parse and display task status')
@click.argument('filters', nargs=-1)
def status(filters):
    """
    Parse and display task status

    If any FILTERS are specified, show status only for tasks with matching prefixes/names
    """

    session = EjudgeSession()
    problems = ejudge_summary(session)

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
    row_format = "{:8} {:35} {:20} {:>5}"
    table.show(problems)
