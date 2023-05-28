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
@click.option('-f', '--first-contest', 'first_contest_', type=str,
              help='Show score for all contests since the chosen one (module 4 begins with sm11)')
def my_score(K, year, first_contest_):
    user = None
    try:
        session = EjudgeSession()
        standings = ejudge_standings(session)
        user = standings.user
    except (EjudgeUnavailableError, AuthError) as err:
        click.secho(
            f'Cannot get standings from ejudge. Reason: {err.message}', fg='yellow', err=True
        )
        return
    standings = get_global_standings(user, year)
    top1_score = get_top1_score(standings, first_contest_)
    my_score = get_my_score(standings, first_contest_)
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
        str(real_score) + '/9.0', fg=fg, bold=True))


def get_top1_score(standings, first_contest_):
    contests = None
    if first_contest_:
        contests = select_contests_starting_from_specific_contest(
            standings, first_contest_)

    scores = []
    for row in standings.rows:
        score = 0
        for task in row.tasks:
            if is_ranked_contest(task.contest) and task.score is not None:
                if first_contest_:
                    if task.contest in contests:
                        score += int(task.score)
                else:
                    score += int(task.score)    
        scores.append(score)
    return max(scores)


def get_my_score(standings, first_contest=None):
    contests = None
    if first_contest:
        contests = select_contests_starting_from_specific_contest(
            standings, first_contest)

    for row in standings.rows:
        if row.is_self:
            if contests:
                return sum(int(task.score) for task in row.tasks if task.contest in contests and task.score)
            else:
                return row.score

    raise ValueError("Couldn't find user in standings")


def is_ranked_contest(contest):
    return contest.startswith('kr') or contest.startswith('sm') or contest.startswith('ku')


def select_contests_starting_from_specific_contest(standings, first_contest_):
    contests = []
    for contest in standings.contests[::-1]:
        # kr04 идет после контестов за 4 модуль, но относится к 3 модулю. Не понятно как такое отслеживать не вручную
        # Пока просто убрал ее, потому что сейчас интересен только 4 модуль
        if not (contest.startswith('exam') or contest == 'kr04' or contest == 'ku04'):
            contests.append(contest)
            if contest == first_contest_:
                break

    return contests
