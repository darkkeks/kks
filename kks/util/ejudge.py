import json
import pickle
import re
import click

from kks import __version__
from kks.ejudge import LinkTypes, AuthData, get_contest_url
from kks.util.common import config_directory, read_config, write_config
from kks.errors import AuthError, APIError


def load_auth_data():
    config = read_config()
    if not config.has_section('Auth'):
        return None
    auth = config['Auth']
    if 'login' in auth and 'contest' in auth:
        return AuthData(auth['login'], auth['contest'], auth.get('password', None))
    return None


def save_auth_data(auth_data, store_password=True):
    config = read_config()
    config['Auth'] = {
        'login': auth_data.login,
        'contest': auth_data.contest_id
    }

    if store_password and auth_data.password is not None:
        config['Auth']['password'] = auth_data.password

    write_config(config)


def load_links():
    config = read_config()
    if config.has_section('Links'):
        return config['Links']
    return None


def save_links(links):
    config = read_config()
    config['Links'] = links
    write_config(config)


def load_session():
    import requests

    cookies = config_directory() / 'cookies.pickle'
    if not cookies.is_file():
        return None

    session = requests.session()
    with open(cookies, 'rb') as f:
        try:
            cookies = pickle.load(f)
        except Exception:
            return None
        session.cookies.update(cookies)
    return session


def store_session(session):
    cookies = config_directory() / 'cookies.pickle'
    with open(cookies, 'wb') as f:
        pickle.dump(session.cookies, f)


class RunStatus:
    """A (very) limited wrapper class for responses from "run-status-json" method"""

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

    CHECK_FAILED = 6
    PARTIAL = 7
    ACCEPTED = 8
    IGNORED = 9
    PENDING = 11

    PENDING_REVIEW = 16
    REJECTED = 17
    SKIPPED = 18

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
        CHECK_FAILED: 'Check failed',
        PARTIAL: 'Partial solution',
        ACCEPTED: 'Accepted for testing',
        IGNORED: 'Ignored',
        PENDING: 'Pending check',
        PENDING_REVIEW: 'Pending review',
        REJECTED: 'Rejected',
        SKIPPED: 'Skipped'
    }

    @staticmethod
    def get_description(status_code):
        return RunStatus._descriptions.get(status_code, f'Unknown status {status_code}')

    def __init__(self, run_status):
        self.status = run_status['run']['status']
        self.tests = []
        if 'testing_report' in run_status and 'tests' in run_status['testing_report']:
            self.tests = run_status['testing_report']['tests']

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
            test_results = '\n'.join(map(test_descr, [test for test in self.tests if test['status'] not in [self.OK, self.SKIPPED]]))
        else:
            test_results = '\n'.join(map(test_descr, self.tests))
        return f'{self}\n{test_results}'


class API:
    def __init__(self, sids=None):
        import requests

        self._prefix = 'https://caos.ejudge.ru/cgi-bin/'
        self._http = requests.Session()
        self._http.headers = {'User-Agent': f'kokos/{__version__}'}

        self._sids = sids

    def _request(self, url, need_json, **kwargs):
        resp = self._http.post(url, **kwargs)  # all methods accept POST requests
        resp.encoding = 'utf-8'  # ejudge doesn't set encoding header
        try:
            # all methods return errors in json
            data = json.loads(resp.content)
        except ValueError as e:
            if not need_json:
                return resp.content
            raise APIError(f'Invalid response. resp={resp.content}, err={e}', APIError.INVALID_RESPONSE)

        # if a submission is a valid JSON file, then api.download_run will fail
        if not need_json or not data['ok']:
            err = data.get('error', {})
            raise APIError(err.get('message', 'Unknown error'), err.get('num', APIError.UNKNOWN))
        return data['result']

    def _api_method(self, path, action, sids=None, need_json=True, **kwargs):
        """
        Allowed values for `sids`:
          - None (use self._sids)
          - {} (don't use sids)
          - {'EJSID': str, 'SID': str}
        """

        url = self._prefix + path

        data = kwargs.setdefault('data', {})
        data.update({'action': action, 'json': 1})
        if sids is None:
            sids = self._sids
        data.update(sids)

        return self._request(url, need_json, **kwargs)

    def auth(self, creds):
        """get new sids"""
        # NOTE is 1step auth possible?

        def extract_sids(resp):
            return {'EJSID': resp['EJSID'], 'SID': resp['SID']}

        sids = extract_sids(self.login(creds.login, creds.password))
        self._sids = extract_sids(self.enter_contest(sids, creds.contest_id))

    def login(self, login, password):
        """get sids for enter_contest method"""
        data = {
            'login': login,
            'password': password,
        }
        return self._api_method('register', 'login-json', {}, data=data)

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
    sid_regex = re.compile('/S([0-9a-f]{16})')

    def __init__(self, auth=True):
        self._sids = {'SID': None, 'EJSID': None}

        self.http = load_session()
        if self.http is not None:
            self.links = load_links()

        if self.http is None or self.links is None:
            if auth:
                self.auth()
        else:
            self._update_sid()

    def auth(self, auth_data=None, store_password=None):
        if auth_data is None:
            click.secho('Cookies are either missing or invalid, trying to auth with saved data', fg='yellow', err=True)
            auth_data = load_auth_data()

            if auth_data is not None:
                store_password = True
                if auth_data.password is None:
                    store_password = False
                    auth_data.password = click.prompt('Password', hide_input=True)

        if auth_data is None:
            click.secho('No valid cookies or auth data, please use "kks auth" to log in', fg='yellow', err=True)
            raise AuthError()

        import requests
        from bs4 import BeautifulSoup

        if self.http is None:
            self.http = requests.session()
        else:
            self.http.cookies.clear()
        url = get_contest_url(auth_data)
        page = self.http.post(url, data={
            'login': auth_data.login,
            'password': auth_data.password
        })

        if page.status_code != requests.codes.ok:
            click.secho(f'Failed to authenticate (status code {page.status_code})', err=True, fg='red')
            raise AuthError()

        soup = BeautifulSoup(page.content, 'html.parser')

        if 'Invalid contest' in soup.text or 'invalid contest_id' in soup.text:
            click.secho(f'Invalid contest (contest id {auth_data.contest_id})', fg='red', err=True)
            raise AuthError()

        if 'Permission denied' in soup.text:
            click.secho('Permission denied (invalid username, password or contest id)', fg='red', err=True)
            raise AuthError()

        buttons = soup.find_all('a', {'class': 'menu'}, href=True)

        self.links = {
            button.text: button['href']
            for button in buttons
        }

        if self.links is None:
            click.secho('Auth data is invalid, use "kks auth" to authorize', fg='red', err=True)
            raise AuthError()

        save_auth_data(auth_data, store_password)
        save_links(self.links)
        store_session(self.http)
        self._update_sid()

    def api(self):
        """
        Create an API wrapper with (EJ)SID from this session
        If cookies are outdated, api requests will raise an APIError
        If api is used before any session requests are performed, use EjudgeSession.with_auth for the first request
        Example:
        >>> api = session.api()
        >>> problem = session.with_auth(api.problem_status, 123)
        >>> ...
        >>> info = api.contest_status()  # cookies are up to date
        """
        return API(self._sids)

    def with_auth(self, api_method, *args, **kwargs):
        """
        api_method should only a method of API object that was created with .api() method of this instance
        """
        try:
            return api_method(*args, **kwargs)
        except APIError as e:
            if e.code != APIError.INVALID_SESSION:
                raise e
            self.auth()
            return api_method(*args, **kwargs)

    def _update_sid(self):
        sid = EjudgeSession.sid_regex.search(self.links.get(LinkTypes.SUMMARY)).group(1)
        self._sids.update({'SID': sid, 'EJSID':  self.http.cookies['EJSID']})

    def modify_url(self, url):
        return re.sub(EjudgeSession.sid_regex, f"/S{self._sids['SID']}", url, count=1)

    def _request(self, method, url, *args, **kwargs):
        response = method(url, *args, **kwargs)
        if 'Invalid session' in response.text:
            self.auth()
            url = self.modify_url(url)
            response = method(url, *args, **kwargs)
        return response

    def get(self, url, *args, **kwargs):
        return self._request(self.http.get, url, *args, **kwargs)

    def post(self, url, *args, **kwargs):
        return self._request(self.http.post, url, *args, **kwargs)
