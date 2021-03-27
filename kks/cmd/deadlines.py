from datetime import datetime, timedelta
from itertools import groupby

import click

from kks.ejudge import CacheKeys, ejudge_summary, update_cached_problems, PROBLEM_INFO_VERSION
from kks.util.ejudge import EjudgeSession
from kks.util.storage import Cache


@click.command(short_help='Show contest deadlines')
@click.option('-l', '--last', type=int,
              help='Show deadlines for last N contests')
@click.option('-c', '--contest', 'contests', type=str, multiple=True,
              help='Show deadlines for the selected contest')
@click.option('-nc', '--no-cache', is_flag=True,
              help='Reload cached data')
def deadlines(last, contests, no_cache):
    session = EjudgeSession()
    summary = ejudge_summary(session)
    names = [problem.short_name for problem in summary]

    with Cache('problem_info', compress=True, version=PROBLEM_INFO_VERSION).load() as cache:

        if no_cache:
            for problem in summary:
                cache.erase(CacheKeys.deadline(problem.contest()))

        problems = update_cached_problems(cache, names, session, only_contests=True, summary=summary)

    for (contest, _), problem in zip(groupby(summary, lambda p: p.contest()), problems):
        if problem.past_deadline():
            click.secho(f'{contest:} - Past Deadline', fg='red')
        elif problem.deadlines.soft is not None:
            deadline = problem.deadlines.soft.strftime('%Y/%m/%d %H:%M:%S')  # TODO is timezone always MSK?
            dt = problem.deadlines.soft - datetime.now()
            color = 'bright_yellow' if dt > timedelta(days=1) else 'orange'
            # TODO show penalty
            click.secho(f'{contest:} - Next deadline is {deadline}', fg=color)
        else:
            click.secho(f'{contest:} - No deadlines yet', fg='green')
