#!/usr/bin/env python3
import sys
from pathlib import Path

from kks.util.ejudge import EjudgeSession
from kks.util.fancytable import FancyTable, StaticColumn
from kks.ejudge import ejudge_submissions_judge


BASE_DIR = Path(__file__).resolve().parent
ID_FILE = BASE_DIR/'last_run_id'


def new_submissions():
    """Gets new submissions in chronological order"""
    last_id = -1
    if ID_FILE.exists():
        last_id = int(ID_FILE.read_text())
    session = EjudgeSession()
    # - If last_run is greater than id of the last existing run (no new submissions)
    #   and filter expression is empty, ejudge will return the last run anyway.
    # - Without last_run ejudge will return at most 20 latest submissions.
    return ejudge_submissions_judge(session, f'id > {last_id}', 0, -1)


def save_last_id(submissions, id_file=None):
    if not submissions:
        return
    if id_file is None:
        id_file = ID_FILE
    with open(id_file, 'w') as f:
        f.write(str(submissions[-1].id))


if __name__ == '__main__':
    submissions = new_submissions()
    if not submissions:
        print('No new submissions!')
        sys.exit(0)
    table = FancyTable()
    table.add_column(StaticColumn('ID', 5, lambda sub: sub.id, right_just=False))
    table.add_column(StaticColumn('Time', len('--/--/---- --:--:--'), lambda sub: sub.time, right_just=False))
    table.add_column(StaticColumn.padding(3))
    table.add_column(StaticColumn('User', 35, lambda sub: sub.user, right_just=False))
    table.add_column(StaticColumn('Problem', 6, lambda sub: sub.problem, right_just=False))
    table.add_column(StaticColumn('Status', 24, lambda sub: sub.status, right_just=False))
    table.add_column(StaticColumn('Tests', 2, lambda sub: sub.tests_passed, right_just=False))
    table.add_column(StaticColumn('Score', 3, lambda sub: sub.score, right_just=False))
    table.show(submissions)
