import json
from base64 import b64decode
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import click

from kks import __version__
from kks.ejudge import AuthData, Links, Page, get_contest_url
from kks.errors import EjudgeUnavailableError, AuthError, APIError
from kks.util.storage import Config, PickleStorage


def load_auth_data():
    auth = Config().auth
    if auth.login:
        return AuthData(auth.login, auth.contest, auth.password)
    return None


def save_auth_data(auth_data, store_password=True):
    config = Config()
    config.auth.login = auth_data.login
    config.auth.contest = auth_data.contest_id
    if store_password and auth_data.password is not None:
        config.auth.password = auth_data.password
    else:
        del config.auth.password
    config.save()


def check_response(resp):
    # will not raise on auth errors (ejudge does not change the status code)
    if not resp.ok:
        raise EjudgeUnavailableError


class RunStatus:
    """A (very) limited wrapper class for responses from "run-status-json" method"""

    # TODO use enum?
    COMPILING = 98  # from github.com/blackav/ejudge-fuse
    COMPILED = 97
    RUNNING = 96

    # this group is also used in test results
    OK = 0
    CE = 1
    RE = 2
    TL = 3
    PE = 4
    WA = 5
    ML = 12
    WT = 15

    CHECK_FAILED = 6
    PARTIAL = 7
    ACCEPTED = 8
    IGNORED = 9
    PENDING = 11
    STYLE_ERR = 14
    PENDING_REVIEW = 16
    REJECTED = 17
    SKIPPED = 18
    SYNC_ERR = 19

    # There are more, but only these were seen on caos.ejudge.ru

    _descriptions = {
        COMPILING: 'Compiling',
        COMPILED: 'Compiled',
        RUNNING: 'Running',
        OK: 'OK',
        CE: 'Compilation error',
        RE: 'Runtime error',
        TL: 'Time limit exceeded',
        PE: 'Presentation error',
        WA: 'Wrong answer',
        ML: 'Memory limit exceeded',
        WT: 'Wall time-limit exceeded',
        CHECK_FAILED: 'Check failed',
        PARTIAL: 'Partial solution',
        ACCEPTED: 'Accepted for testing',
        IGNORED: 'Ignored',
        PENDING: 'Pending check',
        STYLE_ERR: 'Coding style violation',
        PENDING_REVIEW: 'Pending review',
        REJECTED: 'Rejected',
        SKIPPED: 'Skipped',
        SYNC_ERR: 'Synchronization error'
    }

    @staticmethod
    def get_description(status_code):
        return RunStatus._descriptions.get(status_code, f'Unknown status {status_code}')

    def __init__(self, run_status):
        self.status = run_status['run']['status']

        self.tests = []
        if 'testing_report' in run_status and 'tests' in run_status['testing_report']:
            self.tests = run_status['testing_report']['tests']

        self.compiler_output = 'Compiler output is not available'
        if 'compiler_output' in run_status and 'content' in run_status['compiler_output']:
            data = run_status['compiler_output']['content'].get('data', '')
            try:
                self.compiler_output = b64decode(data).decode()
            except Exception:
                self.compiler_output = 'Cannot decode compiler output: {data}'

    def is_testing(self):
        return self.status >= 95 and self.status <= 99

    def __str__(self):
        return self.get_description(self.status)

    def with_tests(self, failed_only=False):
        if not self.tests:
            return str(self)

        def test_descr(test):
            return f"{test['num']} - {self.get_description(test['status'])}"

        if failed_only:
            test_results = '\n'.join(
                test_descr(test)
                for test in self.tests if test['status'] not in [self.OK, self.SKIPPED]
            )
        else:
            test_results = '\n'.join(map(test_descr, self.tests))
        return f'{self}\n{test_results}'

    def with_compiler_output(self):
        return f'{self}\n\nCompiler output:\n{self.compiler_output}'


class Sids:
    def __init__(self, sid, ejsid):
        self.sid = sid
        self.ejsid = ejsid

    @classmethod
    def from_dict(cls, data):
        return cls(data['SID'], data['EJSID'])

    def as_dict(self):
        return {'SID': self.sid, 'EJSID': self.ejsid}


class API:
    def __init__(self, sids=None):
        import requests

        self._prefix = Links.CGI_BIN+'/'
        self._http = requests.Session()
        self._http.headers = {'User-Agent': f'kokos/{__version__}'}

        self._sids = sids

    def _request(self, url, need_json, **kwargs):
        resp = self._http.post(url, **kwargs)  # all methods accept POST requests
        resp.encoding = 'utf-8'  # ejudge doesn't set encoding header
        check_response(resp)
        try:
            # all methods return errors in json
            data = json.loads(resp.content)
        except ValueError as e:
            if not need_json:
                return resp.content
            raise APIError(
                f'Invalid response. resp={resp.content}, err={e}', APIError.INVALID_RESPONSE
            )

        # if a submission is a valid JSON file, then api.download_run will fail
        if not need_json or not data['ok']:
            err = data.get('error', {})
            raise APIError(err.get('message', 'Unknown error'), err.get('num', APIError.UNKNOWN))
        return data['result']

    def _api_method(self, path, action, sids=None, need_json=True, use_sids=True, **kwargs):
        """
        if sids is None and use_sids is True, will use self._sids
        """

        url = self._prefix + path

        data = kwargs.setdefault('data', {})
        data.update({'action': action, 'json': 1})
        if use_sids:
            if sids is None:
                sids = self._sids
            data.update(sids.as_dict())

        return self._request(url, need_json, **kwargs)

    def auth(self, creds: AuthData):
        """get new sids"""
        # NOTE is 1step auth possible?

        top_level_sids = Sids.from_dict(self.login(creds.login, creds.password))
        self._sids = Sids.from_dict(self.enter_contest(top_level_sids, creds.contest_id))

    def login(self, login, password):
        """get sids for enter_contest method"""
        data = {
            'login': login,
            'password': password,
        }
        return self._api_method('register', 'login-json', data=data, use_sids=False)

    def enter_contest(self, sids, contest_id):
        data = {
            'contest_id': contest_id
        }
        return self._api_method('register', 'enter-contest-json', sids, data=data)

    def contest_status(self):
        return self._api_method('client', 'contest-status-json')

    def problem_status(self, prob_id):
        data = {
            'problem': int(prob_id)
        }
        return self._api_method('client', 'problem-status-json', data=data)

    def problem_statement(self, prob_id):
        data = {
            'problem': int(prob_id)
        }
        return self._api_method('client', 'problem-statement-json', data=data, need_json=False)

    def list_runs(self, prob_id=None):
        # newest runs go first
        # if no prob_id is passed then all runs are returned (useful for sync?)
        if prob_id is None:
            return self._api_method('client', 'list-runs-json')['runs']
        data = {
            'prob_id': int(prob_id)
        }
        return self._api_method('client', 'list-runs-json', data=data)['runs']

    def run_status(self, run_id):
        data = {
            'run_id': int(run_id)
        }
        return self._api_method('client', 'run-status-json', data=data)

    def download_run(self, run_id):
        data = {
            'run_id': int(run_id)
        }
        return self._api_method('client', 'download-run', data=data, need_json=False)

    def run_messages(self, run_id):
        data = {
            'run_id': int(run_id)
        }
        return self._api_method('client', 'run-messages-json', data=data)

    # run-test-json - test results? unknown params

    def submit(self, prob_id, file, lang):
        data = {
            'prob_id': int(prob_id),
        }
        if lang is not None:  # NOTE may possibly break on problems without lang (see sm01-3)
            data['lang_id'] = int(lang)

        files = {
            'file': (file.name, open(file, 'rb'))
        }
        return self._api_method('client', 'submit-run', data=data, files=files)


class EjudgeSession:
    def __init__(self, auth=True):
        import requests
        self.http = requests.session()

        self._storage = PickleStorage('storage')
        self.sids = self._load_sids() or Sids(None, None)

        if self.sids.sid and self.sids.ejsid:
            self.http.cookies.set('EJSID', self.sids.ejsid, domain=Links.HOST)
        elif auth:
            self.auth()

    def auth(self, auth_data=None):
        if auth_data is None:  # auto-auth
            auth_data = load_auth_data()
            if auth_data is None:
                raise AuthError(
                    'Auth data is not found, please use "kks auth" to log in', fg='yellow'
                )

            click.secho(
                'Ejudge session is missing or invalid, trying to auth with saved data',
                fg='yellow', err=True
            )
            if auth_data.password is None:
                auth_data.password = click.prompt('Password', hide_input=True)

        import requests

        self.http.cookies.clear()
        url = get_contest_url(auth_data)
        page = self.http.post(url, data={
            'login': auth_data.login,
            'password': auth_data.password
        })

        if page.status_code != requests.codes.ok:
            raise AuthError(f'Failed to authenticate (status code {page.status_code})')

        if 'Invalid contest' in page.text or 'invalid contest_id' in page.text:
            raise AuthError(f'Invalid contest (contest id {auth_data.contest_id})')

        if 'Permission denied' in page.text:
            raise AuthError('Permission denied (invalid username, password or contest id)')

        self._update_sids(page.url)
        self._store_sids()

    def api(self):
        """
        Create an API wrapper with (EJ)SID from this session
        If cookies are outdated, api requests will raise an APIError
        If api is used before any session requests are performed,
        use EjudgeSession.with_auth for the first request/
        Example:
        >>> api = session.api()
        >>> problem = session.with_auth(api.problem_status, 123)
        >>> ...
        >>> info = api.contest_status()  # cookies are up to date
        """
        return API(self.sids)

    def with_auth(self, api_method, *args, **kwargs):
        """Calls the API method, updates auth data if needed.

        Args:
            api_method: A method of an API object
                that was returned from `self.api()`.
                If any other API object is used, results are undefined.
        """
        try:
            return api_method(*args, **kwargs)
        except APIError as e:
            if e.code == APIError.INVALID_SESSION:
                self.auth()
                return api_method(*args, **kwargs)
            raise e

    @staticmethod
    def needs_auth(url):
        return 'SID' in parse_qs(urlsplit(url).query)

    def _update_sids(self, url):
        self.sids.sid = parse_qs(urlsplit(url).query)['SID'][0]
        self.sids.ejsid = self.http.cookies['EJSID']

    def _store_sids(self):
        with self._storage.load() as storage:
            storage.set('sids', self.sids)

    def _load_sids(self):
        with self._storage.load() as storage:
            return storage.get('sids')

    def _request(self, method, url, *args, **kwargs):
        # NOTE params should only be passed as a keyword argument
        params = kwargs.get('params', {}).copy()
        # If SID is included in the url, move it to params
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        if 'SID' in query:
            params['SID'] = query.pop('SID')[0]
            url = urlunsplit(parts._replace(query=urlencode(query, doseq=True)))
        params['SID'] = self.sids.sid
        page_id: Optional[Page] = kwargs.pop('page_id', None)
        if page_id is not None:
            params['action'] = page_id.value
        kwargs['params'] = params

        response = method(url, *args, **kwargs)
        check_response(response)
        # the requested page may contain binary data (e.g. problem attachments)
        if b'Invalid session' in response.content:
            self.auth()
            params['SID'] = self.sids.sid
            response = method(url, *args, **kwargs)
        return response

    def get(self, url, *args, **kwargs):
        if args:
            kwargs['params'] = args[0]
            args = args[1:]
        return self._request(self.http.get, url, *args, **kwargs)

    def post(self, url, *args, **kwargs):
        return self._request(self.http.post, url, *args, **kwargs)

    def get_page(self, page_id: Page, *args, **kwargs):
        return self.get(Links.WEB_CLIENT_ROOT, *args, page_id=page_id, **kwargs)

    def post_page(self, page_id: Page, *args, **kwargs):
        return self.post(Links.WEB_CLIENT_ROOT, *args, page_id=page_id, **kwargs)
