import re
from collections import namedtuple
from itertools import groupby

import click
from tqdm import tqdm

from kks.ejudge import LinkTypes, Status, ejudge_standings, ejudge_summary, get_problem_info, extract_contest_name
from kks.util.common import read_config, write_config, set_boolean_option, get_boolean_option, has_boolean_option
from kks.util.ejudge import EjudgeSession
from kks.errors import AuthError
from kks.util.cache import Cache
from kks.util.stat import send_standings, get_global_standings

GLOBAL_OPT_OUT = 'global-opt-out'

Problem = namedtuple('Problem', ['href', 'short_name', 'contest'])  # used for caching the problem list


ROW_FORMAT = "{:>6}  {:25} {:>7} {:>6}{}"
PREFIX_LENGTH = sum([6, 2, 25, 1, 7, 1, 6])
CONTEST_DELIMITER = ' | '


@click.command(short_help='Parse and display user standings')
@click.option('-l', '--last', type=int,
              help='Print result of last N contest')
@click.option('-a', '--all', 'all_', is_flag=True,
              help='Print result of all contests')
@click.option('-c', '--contest', 'contests', type=str, multiple=True,
              help='Print the results of the selected contest')
@click.option('-m', '--max',  'max_', is_flag=True,
              help='Print maximal possible scores (based on current deadlines)')
@click.option('-nc', '--no-cache', is_flag=True,
              help='Clear cache and reload task info (used with --max)')
@click.option('-g', '--global', 'global_', is_flag=True,
              help='Use global standings instead of group one. May be outdated')
@click.option('--global-opt-out', is_flag=True,
              help='Opt out from submitting your group results')
def top(last, contests, all_, max_, no_cache, global_, global_opt_out):
    """
    Parse and display user standings

    \b
    Example usage:
        kks top
        kks top --all
        kks top -c sm01 -c sm02
        kks top --last 2
    """

    config = read_config()

    if global_opt_out:
        if click.confirm('Do you really want to opt out from sending your group standings to kks.darkkeks.me?'):
            set_boolean_option(config, GLOBAL_OPT_OUT, True)
            write_config(config)
            click.secho('Successfully disabled standings sending. You can always enable sending by manually editing '
                        '~/.kks/config.ini', color='red', err=True)
        return
    elif not has_boolean_option(config, GLOBAL_OPT_OUT):
        click.secho('Standings can be sent for aggregation to kks api. '
                    'This allows us to create global standings (you can try it out with kks top --global)', err=True)
        click.secho('You can always disable sending using kks top --global-opt-out', err=True)
        if click.confirm('Do you want to send group standings to kks api?', default=True):
            click.secho('Thanks a lot for you contribution! We appreciate it!', color='green', err=True)
            set_boolean_option(config, GLOBAL_OPT_OUT, False)
            write_config(config)
        else:
            click.secho('Successfully disabled standings sending. You can always enable sending by manually editing '
                        '~/.kks/config.ini', color='red', err=True)
            set_boolean_option(config, GLOBAL_OPT_OUT, True)
            write_config(config)

    try:
        session = EjudgeSession()
    except AuthError:
        return

    standings = ejudge_standings(session)
    if standings is None:
        return

    if not get_boolean_option(config, GLOBAL_OPT_OUT):
        if not send_standings(standings):
            click.secho('Failed to send standings to kks api', color='yellow', err=True)

    if global_:
        standings = get_global_standings()
        if standings is None:
            click.secho('Standings are not available now :(', color='yellow', err=True)
            return

    if max_:
        standings = estimate_max(standings, session, no_cache)

    display_standings(standings, last, contests, all_)


def display_standings(standings, last, contests, all_):
    contests = select_contests(standings, last, contests, all_)
    if contests is None:
        return

    contest_widths = get_contest_widths(standings.contests, standings.tasks_by_contest)
    contests_header = ''.join([
        CONTEST_DELIMITER + contest.ljust(contest_widths[contest], ' ')
        for contest in contests
    ])
    header = ROW_FORMAT.format("Place", "User", "Solved", "Score", contests_header)

    click.secho(header, fg='white', bold=True)

    for row in standings.rows:
        tasks = ''.join([
            click.style(CONTEST_DELIMITER, fg=row.color(), bold=row.bold()) + ' '.join([
                click.style('{:>3}'.format(task.table_score() or ''), fg=task.color(), bold=task.bold())
                for task in tasks
            ])
            for contest, tasks in groupby(row.tasks, lambda task: task.contest)
            if contest in contests
        ])

        string = ROW_FORMAT.format(row.place, row.user, row.solved, row.score, tasks)
        click.secho(string, fg=row.color(), bold=row.bold())


def select_contests(standings, last, contests, all_):
    has_last = last is not None
    has_contests = len(contests) > 0

    if sum([has_last, has_contests, all_]) > 1:
        click.secho('Arguments are exclusive, specify no more than one')
        return None

    if all_:
        return standings.contests

    if has_contests:
        def is_available(contest):
            if contest not in standings.contests:
                click.echo(
                        click.style('Contest ', fg='red') +
                        click.style(contest, fg='blue', bold=True) +
                        click.style(' not found!', fg='red'),
                        err=True
                )
            return contest in standings.contests

        return list(filter(is_available, contests))

    last = last or get_default_contest_count(standings.contests, standings.tasks_by_contest)

    return standings.contests[-last:] if last > 0 else []


def get_default_contest_count(contests, tasks_by_contest):
    """По ширине терминала пытается определить, сколько колонок можно вывести"""
    (width, _) = click.get_terminal_size()

    delimiter_width = len(CONTEST_DELIMITER)
    contest_widths = get_contest_widths(contests, tasks_by_contest)

    width_sum = 0
    for i, contest in enumerate(contests[::-1]):
        width_sum += delimiter_width + contest_widths[contest]
        if width_sum + PREFIX_LENGTH > width:
            return i

    return len(contests)


def get_contest_widths(contests, tasks_by_contest):
    return {
        contest: len('100') * len(tasks_by_contest[contest]) + len(tasks_by_contest[contest]) - 1
        for contest in contests
    }


def estimate_max(standings, session, force_reload):
    # NOTE may produce incorrect results for "krxx" contests (they may be reopened?)

    sid_regex = re.compile('/S([0-9a-f]{16})')
    sid = sid_regex.search(session.links.get(LinkTypes.USER_STANDINGS)).group(1)

    def cached_problem(problem):
        href = re.sub(sid_regex, '/S__SID__', problem.href, count=1)
        return Problem(href, problem.short_name, extract_contest_name(problem.short_name))

    def with_fixed_href(problem):
        href = problem.href.replace('__SID__', sid)
        return Problem(href, problem.short_name, problem.contest)

    standings.rows = list(standings.rows)

    with Cache('problem_info', compress=True).load() as cache:
        if force_reload:
            cache.clear()

        problem_list = cache.get('problem_links', [])  # we can avoid loading summary

        with tqdm(total=len(standings.tasks), leave=False) as pbar:
            def with_progress(func, *args, **kwargs):
                result = func(*args, **kwargs)
                pbar.update(1)
                return result

            if len(problem_list) != len(standings.tasks) or \
                    any(problem.short_name != task.name for problem, task in zip(problem_list, standings.tasks)):
                problem_list = ejudge_summary(session)
                problem_list = [cached_problem(p) for p in problem_list]
                cache.set('problem_links', problem_list)
            problems = [with_progress(get_problem_info, with_fixed_href(problem), cache, session) for problem in problem_list]

    for row in standings.rows:
        for task_score, problem in zip(row.tasks, problems):
            if task_score.score is None or task_score.score == '0':
                if task_score.status == Status.REJECTED:
                    max_score = problem.full_score
                else:
                    max_score = problem.full_score - problem.current_penalty
                    if task_score.score == '0':
                        max_score -= problem.run_penalty
                        # actually may be lower
                if max_score > 0:
                    row.solved += 1
                    row.score += max_score
                    task_score.score = max_score
                    task_score.status = Status.REVIEW

    standings.rows.sort(key=lambda x: (x.score, x.solved), reverse=True)
    for i, row in enumerate(standings.rows):
        row.place = i + 1

    return standings
