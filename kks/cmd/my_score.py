import re

import click

from kks.ejudge import ejudge_standings
from kks.errors import AuthError, EjudgeUnavailableError
from kks.util.ejudge import EjudgeSession
from kks.util.stat import get_global_standings


@click.command(short_help='Calculate your score from homeworks')
@click.option('-b', '--barrier', 'K', type=int, default=5000,
              help='K_i param. See http://wiki.cs.hse.ru/CAOS-2022#.D0.A4.D0.BE.D1.80.D0.BC.D1.83.D0.BB.D0.B0_.D0.BE.D1.86.D0.B5.D0.BD.D0.BA.D0.B8')
@click.option('-y', '--year', type=int, default=2022,
              help='Show standings for the selected year')
def my_score(K, year):
    user = None
    try:
        session = EjudgeSession()
        standings = ejudge_standings(session)
        # TODO call send_standings if opted in
        user = standings.user
    except (EjudgeUnavailableError, AuthError) as err:
        click.secho(
            f'Cannot get standings from ejudge. Reason: {err.message}', fg='yellow', err=True
        )
        return
    standings = get_global_standings(user, year)
    top1_score = get_top1_score(standings)
    my_score = get_my_score(standings)
    real_score = None
    if my_score < K:
        real_score = 6.0 * (my_score / K)
    else:
        real_score = min(9.0, 6.0 + 3.0 * (my_score - K) / (top1_score - K))
    fg = None
    if real_score < 4.0:
        fg = "red"
    elif real_score < 8.0:
        fg = "yellow"
    else:
        fg = "green"
    print('Your estimated score from homework is: ', click.style(str(real_score) + '/9.0', fg=fg, bold=True))


def get_top1_score(standings):
    scores = []
    for row in standings.rows:
        score = 0
        for task in row.tasks:
            if is_rated_contest(task.contest) and task.score is not None:
                score += int(task.score)
        scores.append(score)
    return max(scores)


def get_my_score(standings):
    for row in standings.rows:
        if row.is_self:
            return row.score
    return 0  # No submissions, something else?


def is_rated_contest(contest: str) -> bool:
    # assuming there can be split contests, like sm12.3-1, sm12_3-1, ...
    #
    return re.match(r'^(sm|kr|ku)\d', contest) is not None
