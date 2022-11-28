import json
from base64 import b64decode
from dataclasses import asdict, dataclass
from enum import Enum
from os import environ
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlsplit

import click

from kks import __version__
from kks.errors import EjudgeError, EjudgeUnavailableError, AuthError, APIError
from kks.util.common import deprecated
from kks.util.storage import Config, PickleStorage


"""
This module contains:
- Core ejudge datatypes and enums (AuthData, Links, Lang, Page, RunStatus, ...)
- Request wrappers (API, EjudgeSession)
"""


@deprecated(replacement='AuthData.load_from_config')
def load_auth_data():
    return AuthData.load_from_config()


@deprecated(replacement='AuthData.save_to_config')
def save_auth_data(auth_data, store_password=True):
    return auth_data.save_to_config(store_password=store_password)


def _check_response(resp):
    # will not raise on auth errors (ejudge does not change the status code)
    if not resp.ok:
        raise EjudgeUnavailableError


@dataclass
class AuthData:
    login: str
    password: Optional[str]
    contest_id: int

    @classmethod
    def load_from_config(cls) -> Optional['AuthData']:
        auth = Config().auth
        if auth.login:
            data = auth.asdict()
            data['contest_id'] = data.pop('contest')  # for compatibility with master
            return cls(**data)
        return None

    def save_to_config(self, store_password=True):
        config = Config()
        data = asdict(self)
        data['contest'] = data.pop('contest_id')
        config.auth.update(data)
        if not store_password or self.password is None:
            del config.auth.password
        config.save()


class Lang(Enum):
    def __new__(cls, value, suf):
        obj = object.__new__(cls)
        obj._value_ = value
        obj.suf = suf
        obj._realname = None
        return obj

    @property
    def name(self):
        if self._realname is None:
            self._realname = self._name_.replace('xx', '++').replace('_', '-')
        return self._realname

    # NOTE compiler ids may change
    gcc = 2, '.c'
    gxx = 3, '.cpp'
    python = 13, '.py'
    perl = 14, '.pl'
    ruby = 21, '.rb'
    python3 = 23, '.py'
    make = 25, '.tar'
    gcc_vg = 28, '.c'
    gxx_vg = 29, '.cpp'
    clang = 51, '.c'
    clangxx = 52, '.cpp'
    make_vg = 54, '.tar'
    gcc_32 = 57, '.c'
    clang_32 = 61, '.c'
    clangxx_32 = 62, '.cpp'
    gas_32 = 66, '.S'
    gas = 67, '.S'
    rust = 70, '.rs'
    gas_aarch64 = 101, '.S'
    gas_armv7l = 102, '.S'


class Links:
    """
    Ejudge links.

    All methods accept base_url in "scheme://host[:port]" format.
    Constants are formed using `KKS_CUSTOM_URL` envvar or the default base URL.
    """

    BASE_URL: str
    HOST: str
    CGI_BIN: str
    WEB_CLIENT_ROOT: str

    @classmethod
    def host(cls, base_url):
        return urlsplit(base_url).netloc

    @classmethod
    def cgi_bin(cls, base_url):
        return f'{base_url}/cgi-bin'

    @classmethod
    def web_client_root(cls, base_url):
        return f'{cls.cgi_bin(base_url)}/new-client'

    @classmethod
    def contest_root(cls, base_url=None):
        # Used in kks-judge
        if base_url is None:
            base_url = cls.BASE_URL
        return cls.web_client_root(base_url)

    @classmethod
    def contest_login(cls, auth_data, base_url=None, *, include_creds=False):
        root = cls.contest_root(base_url)
        params = cls._login_params(auth_data)
        if include_creds and auth_data.login is not None and auth_data.password is not None:
            params.update({'login': auth_data.login, 'password': auth_data.password})
        return f'{root}?{urlencode(params)}'

    @classmethod
    def _get_base_url(cls):
        url = environ.get('KKS_CUSTOM_URL')
        if url is None:
            return 'https://caos.myltsev.ru'
        # Remove path and/or trailing slash(es) from envvar
        return urlsplit(url)._replace(path='', query='', fragment='').geturl()

    @classmethod
    def _init_constants(cls):
        cls.BASE_URL = cls._get_base_url()
        for name in cls.__annotations__.keys():
            if name != 'BASE_URL':
                link_generator = getattr(cls, name.lower())
                setattr(cls, name, link_generator(cls.BASE_URL))

    @classmethod
    def _login_params(cls, auth_data):
        return {'contest_id': auth_data.contest_id}


Links._init_constants()


class Page(Enum):
    # Values of NEW_SRV_ACTION_* in include/ejudge/new_server_proto.h
    MAIN_PAGE = 2
    VIEW_SOURCE = 36
    DOWNLOAD_SOURCE = 91
    USER_STANDINGS = 94
    SUMMARY = 137
    SUBMISSIONS = 140
    SUBMIT_CLAR = 141
    CLARS = 142
    SETTINGS = 143


class RunStatus(Enum):
    """Numerical run status. Returned by "run-status-json" API method and used by privileged methods."""

    def __new__(cls, value, description=None):
        obj = object.__new__(cls)
        obj._value_ = value
        obj._description = description
        return obj

    @property
    def description(self):
        if self._description is not None:
            return self._description
        return self._name_.replace('_', ' ').capitalize()

    # from github.com/blackav/ejudge-fuse and ejudge source
    COMPILING = 98
    COMPILED = 97
    RUNNING = 96

    # this group is also used in test results
    OK = 0, 'OK'
    CE = 1, 'Compilation error'
    RE = 2, 'Runtime error'
    TL = 3, 'Time limit exceeded'
    PE = 4, 'Presentation error'
    WA = 5, 'Wrong answer'
    ML = 12, 'Memory limit exceeded'
    WT = 15, 'Wall time-limit exceeded'

    CHECK_FAILED = 6
    PARTIAL = 7, 'Partial solution'
    ACCEPTED = 8, 'Accepted for testing'
    IGNORED = 9
    DISQUALIFIED = 10
    PENDING = 11, 'Pending check'
    SEC_ERR = 13, 'Security violation'
    STYLE_ERR = 14, 'Coding style violation'
    PENDING_REVIEW = 16
    REJECTED = 17
    SKIPPED = 18  # also used for tests
    SYNC_ERR = 19, 'Synchronization error'
    SUMMONED = 23, 'Summoned for defence'

    FULL_REJUDGE = 95  # ?
    REJUDGE = 99
    NO_CHANGE = 100  # NOP? Seen only in status-edit window in judge interface

    # There are more, but only these were seen on caos server


class ExtendedRunStatus:
    """Wrapper class for responses from "run-status-json" method"""

    def __init__(self, run_status: dict):
        self.status = RunStatus(run_status['run']['status'])

        self.tests = run_status.get('testing_report', {}).get('tests', [])

        self.compiler_output = 'Compiler output is not available'
        if 'compiler_output' in run_status and 'content' in run_status['compiler_output']:
            data = run_status['compiler_output']['content'].get('data', '')
            try:
                self.compiler_output = b64decode(data).decode()
            except Exception:
                self.compiler_output = 'Cannot decode compiler output: {data}'

    def is_testing(self):
        return self.status in [
            RunStatus.REJUDGE,
            RunStatus.FULL_REJUDGE,
            RunStatus.COMPILING,
            RunStatus.COMPILED,
            RunStatus.RUNNING,
        ]

    def __str__(self):
        return self.status.description

    def with_tests(self, failed_only=False):
        if not self.tests:
            return str(self)

        def test_descr(test):
            return f"{test['num']} - {RunStatus(test['status']).description}"

        if failed_only:
            test_results = '\n'.join(
                test_descr(test)
                for test in self.tests if RunStatus(test['status']) not in [RunStatus.OK, RunStatus.SKIPPED]
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
    class MethodGroup:
        CLIENT = 'new-client'
        REGISTER = 'register'

    def __init__(self, sids=None, base_url=Links.BASE_URL):
        import requests

        self._prefix = Links.cgi_bin(base_url) + '/'
        self._http = requests.Session()
        self._http.headers = {'User-Agent': f'kokos/{__version__}'}

        self._sids = sids

    def _request(self, url, need_json, **kwargs):
        resp = self._http.post(url, **kwargs)  # all methods accept POST requests
        resp.encoding = 'utf-8'  # ejudge doesn't set encoding header
        _check_response(resp)
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
        return self._api_method(self.MethodGroup.REGISTER, 'login-json', data=data, use_sids=False)

    def enter_contest(self, sids, contest_id):
        data = {
            'contest_id': contest_id
        }
        return self._api_method(self.MethodGroup.REGISTER, 'enter-contest-json', sids, data=data)

    def contest_status(self):
        return self._api_method(self.MethodGroup.CLIENT, 'contest-status-json')

    def problem_status(self, prob_id):
        data = {
            'problem': int(prob_id)
        }
        return self._api_method(self.MethodGroup.CLIENT, 'problem-status-json', data=data)

    def problem_statement(self, prob_id):
        data = {
            'problem': int(prob_id)
        }
        return self._api_method(self.MethodGroup.CLIENT, 'problem-statement-json', data=data, need_json=False)

    def list_runs(self, prob_id=None):
        # newest runs go first
        # if no prob_id is passed then all runs are returned (useful for sync?)
        if prob_id is None:
            return self._api_method(self.MethodGroup.CLIENT, 'list-runs-json')['runs']
        data = {
            'prob_id': int(prob_id)
        }
        return self._api_method(self.MethodGroup.CLIENT, 'list-runs-json', data=data)['runs']

    def run_status(self, run_id):
        data = {
            'run_id': int(run_id)
        }
        return self._api_method(self.MethodGroup.CLIENT, 'run-status-json', data=data)

    def download_run(self, run_id):
        data = {
            'run_id': int(run_id)
        }
        return self._api_method(self.MethodGroup.CLIENT, 'download-run', data=data, need_json=False)

    def run_messages(self, run_id):
        data = {
            'run_id': int(run_id)
        }
        return self._api_method(self.MethodGroup.CLIENT, 'run-messages-json', data=data)

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
        return self._api_method(self.MethodGroup.CLIENT, 'submit-run', data=data, files=files)


class EjudgeSession:
    def __init__(
            self, *,
            auth: bool = True,
            auth_data: Optional[AuthData] = None,
            base_url: str = Links.BASE_URL,
            storage_path: str = 'storage',
    ):
        """
        Args:
            auth: if True and stored auth state is not found, call auth() after initialization.
            auth_data: Optional auth data. If not provided, auth data will be loaded from config.
            base_url: Ejudge URL in "scheme://host[:port]" format.
            storage_path: path to storage file for auth state.
                Path should be relative to kks config dir or absolute.
        """
        import requests
        self.http = requests.Session()

        self._auth_data = auth_data
        self._base_url = base_url
        self._storage = PickleStorage(storage_path)
        self._load_auth_state()

        if self.sids.sid and self.sids.ejsid:
            self.http.cookies.set('EJSID', self.sids.ejsid, domain=urlsplit(self._base_url).netloc)
        elif auth:
            self.auth()

    def auth(self, auth_data: Optional[AuthData] = None):
        """
        Args:
            auth_data: Optional auth data. If present, must have password.
                If None, the session will use auth_data from its constructor or from kks config.
        """
        if auth_data is None:  # auto-auth (on first init or when cookies expire)
            auth_data = self._get_auth_data()

        import requests

        self.http.cookies.clear()
        url = Links.contest_login(auth_data, self._base_url)
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
        self._update_contest_root()
        self._store_auth_state()

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

    def _get_auth_data(self):
        if self._auth_data is not None:
            auth_data = self._auth_data
        else:
            auth_data = AuthData.load_from_config()
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
        return auth_data

    def _update_sids(self, url):
        self.sids.sid = parse_qs(urlsplit(url).query)['SID'][0]
        self.sids.ejsid = self.http.cookies['EJSID']

    def _store_auth_state(self):
        with self._storage.load() as storage:
            storage.set('sids', self.sids)

    def _load_auth_state(self):
        with self._storage.load() as storage:
            self.sids = storage.get('sids') or Sids(None, None)
        self._update_contest_root()

    def _update_contest_root(self):
        # Cache the url to avoid rebuilding it for each request
        # Root url may depend on auth state (kks-judge)
        self._contest_root = Links.contest_root(self._base_url)

    def _request(self, method, url, *args, **kwargs):
        # NOTE params should only be passed as a keyword argument
        params = kwargs.get('params', {}).copy()
        # If SID is included in the url, remove it to avoid conflict with session's SID in params
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        if 'SID' in query:
            query.pop('SID')
            url = parts._replace(query=urlencode(query, doseq=True)).geturl()
        params['SID'] = self.sids.sid
        page_id: Optional[Page] = kwargs.pop('page_id', None)
        if page_id is not None:
            params['action'] = page_id.value
        kwargs['params'] = params

        response = method(url, *args, **kwargs)
        _check_response(response)
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
        return self.get(self._contest_root, *args, page_id=page_id, **kwargs)

    def post_page(self, page_id: Page, *args, **kwargs):
        return self.post(self._contest_root, *args, page_id=page_id, **kwargs)
