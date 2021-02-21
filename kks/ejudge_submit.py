import click

from kks.errors import APIError
from kks.util.common import prompt_choice, with_retries
from kks.util.ejudge import RunStatus


class SubmissionResult:
    OK = 0
    CHECK = 1
    FAIL = 2
    UNKNOWN = 3

    _colors = {OK: 'green', FAIL: 'red', CHECK: 'bright_yellow', UNKNOWN: 'yellow'}

    def __init__(self, status, msg):
        self.status = status
        self.msg = msg

    def color(self):
        return self._colors[self.status]

    @classmethod
    def ok(cls, msg):
        return cls(cls.OK, msg)

    @classmethod
    def check(cls, msg):
        return cls(cls.CHECK, msg)

    @classmethod
    def fail(cls, msg):
        return cls(cls.FAIL, msg)

    @classmethod
    def unknown(cls, msg):
        return cls(cls.UNKNOWN, msg)

    @classmethod
    def parse_status(cls, run_status):
        if run_status.status in [RunStatus.OK, RunStatus.PENDING_REVIEW]:
            return cls.ok(str(run_status))
        if run_status.status in [RunStatus.ACCEPTED, RunStatus.PENDING]:  # PENDING == "Pending check" =?= ACCEPTED
            return cls.check(str(run_status))
        if run_status.status in [RunStatus.CE, RunStatus.STYLE_ERR]:
            return cls.fail(run_status.with_compiler_output())
        return cls.fail(run_status.with_tests(failed_only=True))  # there can be 100+ passed tests and a few failed


def get_lang(available, all_langs):
    def choice(langs):
        choices = [f"{lang['short_name']} - {lang['long_name']}" for lang in langs]
        lang_id = prompt_choice('Select a language / compiler', choices)
        return langs[lang_id]

    if not available:
        return None
    if len(available) == 1:
        return available[0]
    langs = [lang for lang in all_langs if lang['id'] in available]
    return choice(langs)['id']


def submit_solution(session, file, prob_name, timeout):

    @with_retries(step=2, timeout=timeout)
    def get_final_result(api, run_id):
        res = RunStatus(api.run_status(run_id))
        if res.is_testing():
            return None
        return SubmissionResult.parse_status(res)

    api = session.api()
    try:
        contest = session.with_auth(api.contest_status)
    except APIError as e:
        return SubmissionResult.fail(str(e))

    prob_id = None
    for p in contest['problems']:
        if p['short_name'] == prob_name:
            prob_id = p['id']
            break
    if prob_id is None:
        return SubmissionResult.fail('Invalid problem ID')

    problem = api.problem_status(prob_id)
    problem, problem_status = problem['problem'], problem['problem_status']
    if not problem_status.get('is_submittable'):
        return SubmissionResult.fail('Cannot submit a solution for this problem')
    ok_fields = ['is_solved', 'is_pending', 'is_pending_review', 'is_accepted']
    if any(field in problem_status for field in ok_fields) and not click.confirm('This problem was already solved! Submit anyway?'):
        return SubmissionResult.fail('Cancelled by user')

    lang = get_lang(problem.get('compilers', []), contest['compilers'])
    try:
        run_id = api.submit(prob_id, file, lang)['run_id']
    except APIError as e:  # Duplicate / empty file / etc.
        return SubmissionResult.fail(str(e))
    click.secho('Testing...', bold=True)
    return get_final_result(api, run_id) or SubmissionResult.unknown('Testing in progress')
