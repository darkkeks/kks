from time import time, sleep
import click

from kks.errors import APIError, AuthError
from kks.util.common import prompt_choice
from kks.util.ejudge import RunStatus


def is_ok(run_status):
    if run_status['status'] in [RunStatus.OK, RunStatus.PENDING_REVIEW]:
        return True, 'OK'
    if run_status['status'] in [RunStatus.ACCEPTED, RunStatus.PENDING]:  # PENDING == "Pending check" =?= ACCEPTED
        return True, 'Accepted for testing'
    if run_status['status'] == RunStatus.CE:
        return False, 'Compilation error'
    return False, 'Partial solution'


def get_lang(available, all_langs):
    def choice(langs):
        choices = ['{} - {}'.format(e['short_name'], e['long_name']) for e in langs]
        lang_id = prompt_choice('Select a language / compiler', choices)
        return langs[lang_id]

    if not available:
        return None
    if len(available) == 1:
        return available[0]
    langs = [e for e in all_langs if e['id'] in available]
    return choice(langs)['id']


def submit_solution(session, file, prob_name):
    api = session.api()
    try:
        contest = api.contest_status()
    except APIError as e:
        if e.code != APIError.INVALID_SESSION:
            return False, str(e)
        try:
            session.auth()
        except AuthError:
            return False, 'Auth error'
        contest = api.contest_status()  # shouldn't raise errors

    prob_id = None
    for p in contest['problems']:
        if p['short_name'] == prob_name:
            prob_id = p['id']
            break
    if prob_id is None:
        return False, 'Invalid problem ID'

    problem = api.problem_status(prob_id)
    problem, problem_status = problem['problem'], problem['problem_status']
    if not problem_status.get('is_submittable'):
        return False, 'Cannot submit a solution for this problem'
    if (
        'is_solved' in problem_status or
        'is_pending' in problem_status or
        'is_pending_review' in problem_status or
        'is_accepted' in problem_status
       ) and not click.confirm('This problem was already solved! Submit anyway?'):
            return False, 'Cancelled by user'

    lang = get_lang(problem.get('compilers', []), contest['compilers'])
    try:
        res = api.submit(prob_id, file, lang)
    except APIError as e:  # Duplicate / empty file / etc.
        return False, str(e)
    run_id = res['run_id']
    click.secho('Testing...', bold=True)

    dt = 0.5
    retries = int(10 / dt) + 1  # wait 10s max
    for i in range(retries):
        t_start = time()
        res = api.run_status(run_id)['run']
        if not RunStatus.is_testing(res['status']):
            break
        sleep_dt = max(0, t_start + dt - time())
        if sleep_dt:
            sleep(sleep_dt)
    else:
        return True, 'Testing in progress'

    return is_ok(res)
