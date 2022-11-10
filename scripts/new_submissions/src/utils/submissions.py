import typing as t

from kks.util.ejudge import EjudgeSession
from kks.ejudge_priv import ejudge_submissions


def new_submissions(session: EjudgeSession, last_run_id: t.Optional[int]):
    """Gets new submissions in chronological order"""
    if last_run_id is None:
        last_run_id = -1
    # If filter is empty and last_run is greater than id of the last existing run
    #   (there are no new submissions), ejudge will return the last run anyway).
    #   For this reason, `ejudge_submissions(s, first_tun=last_run+1, last_run=-1)` doesn't work
    return ejudge_submissions(session, f'id > {last_run_id}', 0, -1)
