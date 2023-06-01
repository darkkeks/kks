import re

import click

from kks.ejudge import ejudge_standings
from kks.errors import AuthError, EjudgeUnavailableError
from kks.util.ejudge import EjudgeSession
from kks.util.stat import get_global_standings


@click.command(short_help='Calculate your score from homeworks')
@click.option('-b', '--barrier', 'K', type=int, default=3500,
              help='K_i param. See http://wiki.cs.hse.ru/CAOS-2022#.D0.A4.D0.BE.D1.80.D0.BC.D1.83.D0.BB.D0.B0_.D0.BE.D1.86.D0.B5.D0.BD.D0.BA.D0.B8')
@click.option('-y', '--year', type=int, default=2022,
              help='Show standings for the selected year')
@click.option('-f', '--first-contest', type=str,
              help='Show score for all contests since the chosen one (module 4 begins with sm11)')
def my_score(K, year, first_contest):
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
    top1_score = get_top1_score(standings, year, first_contest)
    my_score = get_my_score(standings, year, first_contest)
    real_score = None
    if my_score < K:
        real_score = 6.0 * (my_score / K)
    else:
        real_score = min(9.0, 6.0 + 3.0 * (my_score - K) / (top1_score - K))
    fg = None
    if real_score < 4.0:
        fg = 'red'
    elif real_score < 8.0:
        fg = 'yellow'
    else:
        fg = 'green'
    print('Your current score from homework is: ', click.style(
        str(my_score), fg=fg, bold=True))
    print('Your estimated mark from homework is: ', click.style(
        f'{real_score:.02f}/9.0', fg=fg, bold=True))


def get_top1_score(standings, year, first_contest):
    contests = None
    if first_contest:
        contests = select_contests_starting_from_specific_contest(
            standings, year, first_contest)

    scores = []
    for row in standings.rows:
        score = 0
        for task in row.tasks:
            if is_rated_contest(task.contest) and task.score:
                if first_contest is None or task.contest in contests:
                    score += int(task.score)
        scores.append(score)
    return max(scores)


def get_my_score(standings, year, first_contest):
    contests = None
    if first_contest:
        contests = select_contests_starting_from_specific_contest(standings, year, first_contest)

    for row in standings.rows:
        if row.is_self:
            if contests:
                return sum(int(task.score) for task in row.tasks if task.contest in contests and task.score)
            else:
                return row.score

    return 0


def is_rated_contest(contest: str) -> bool:
    # assuming there can be split contests, like sm12.3-1, sm12_3-1, ...
    return re.match(r'^(sm|kr|ku)\d', contest) is not None


def select_contests_starting_from_specific_contest(standings, year, first_contest):
    contests = []
    for contest in standings.contests[::-1]:
        # В 2022 kr04 шла после контестов за 4 модуль, но относилась к 3 модулю.
        if not (contest.startswith('exam') or ((contest == 'kr04' or contest == 'ku04') and year == 2022)):
            contests.append(contest)
            if contest == first_contest:
                break

    return set(contests)
