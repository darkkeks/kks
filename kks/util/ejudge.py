import inspect
import json
from base64 import b64decode
from copy import copy
from dataclasses import asdict, dataclass
from enum import Enum, Flag, auto
from functools import wraps
from os import environ
from pathlib import Path
from typing import BinaryIO, Optional, Sequence, Tuple, Union
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
    # TODO handle 414 (Request-URI Too Long) separately
    if not resp.ok:
        raise EjudgeUnavailableError


@dataclass
class AuthData:
    login: str
    password: Optional[str]
    contest_id: int
    judge: bool = False

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
    JUDGE_ROOT: str

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
    def judge_root(cls, base_url):
        return f'{cls.cgi_bin(base_url)}/new-judge'

    @classmethod
    def contest_root(cls, base_url=None, *, judge=False):
        if base_url is None:
            base_url = cls.BASE_URL
        if judge:
            return cls.judge_root(base_url)
        return cls.web_client_root(base_url)

    @classmethod
    def contest_login(cls, auth_data, base_url=None, *, include_creds=False):
        root = cls.contest_root(base_url, judge=auth_data.judge)
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
        params = {'contest_id': auth_data.contest_id}
        if auth_data.judge:
            params.update({'role': 5})
        return params


Links._init_constants()


class Page(Enum):
    # Values of NEW_SRV_ACTION_* in include/ejudge/new_server_proto.h
    MAIN_PAGE = 2
    VIEW_SOURCE = 36
    VIEW_REPORT = 37
    SEND_COMMENT = 64
    SET_RUN_STATUS = 67

    REJUDGE_DISPLAYED_CONFIRM = 70  # Confirmation page before REJUDGE_DISPLAYED.
    # No links from other pages. Legacy endpoints, replaced by EDIT_RUN?
    # there are more CHANGE_* actions (user/problem/flags...)
    CHANGE_RUN_PROB_ID = 77
    CHANGE_RUN_LANGUAGE = 79
    CHANGE_RUN_SCORE = 88  # Changes score in VIEW_SOURCE, but not in standings or main page
    CHANGE_RUN_SCORE_ADJ = 89
    REJUDGE_PROBLEM_CONFIRM = 95

    DOWNLOAD_SOURCE = 91
    USER_STANDINGS = 94
    # Bulk rejudge requires some capability from MASTER_SET (REJUDGE_RUN?). TODO check
    REJUDGE_DISPLAYED = 102
    REJUDGE_PROBLEM = 104  # Not implemented (yet?)
    SUMMARY = 137
    SUBMISSIONS = 140
    SUBMIT_CLAR = 141
    CLARS = 142
    SETTINGS = 143
    DOWNLOAD_ARCHIVE_FORM = 148
    DOWNLOAD_ARCHIVE = 149
    CLEAR_DISPLAYED_CONFIRM = 177
    CLEAR_DISPLAYED = 178
    IGNORE_WITH_COMMENT = 233
    OK_WITH_COMMENT = 237
    REJECT_WITH_COMMENT = 238
    SUMMON_WITH_COMMENT = 239
    EDIT_RUN_FORM = 267  # Shows the form with run details. Requires EDIT_RUN capability.
    EDIT_RUN = 268  # Actual "edit" action.
    USERS_AJAX = 278


class RunField(Flag):
    """Field filters for JudgeAPI.list_runs."""
    ID = auto()
    SIZE = auto()
    TIME = auto()
    ABS_TIME = auto()  # In 'list-runs-json' is an alias of TIME
    REL_TIME = auto()
    NSEC = auto()
    USER_ID = auto()
    USER_LOGIN = auto()
    USER_NAME = auto()
    PROB_ID = auto()
    PROB_NAME = auto()
    LANG_ID = auto()
    LANG_NAME = auto()
    IP = auto()
    SHA1 = auto()
    SCORE = auto()
    TEST = auto()
    SCORE_ADJ = auto()
    STATUS = auto()
    VARIANT = auto()
    MIME_TYPE = auto()
    SAVED_SCORE = auto()
    SAVED_TEST = auto()
    SAVED_STATUS = auto()
    UUID = auto()
    EOLN_TYPE = auto()
    STORE_FLAGS = auto()
    TOKENS = auto()

    USER = USER_NAME | USER_LOGIN
    DEFAULT = ID | TIME | USER_NAME | PROB_NAME | LANG_NAME | STATUS | TEST | SCORE


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
    SKIPPED = 18  # Also used for tests
    SYNC_ERR = 19, 'Synchronization error'
    EMPTY = 22, 'EMPTY'  # Cleared runs
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


class BaseAPI:
    """Ejudge API wrapper. Not thread-safe."""

    class _Http(Enum):
        GET = auto()
        POST = auto()

    class _MethodGroup(Enum):
        CLIENT = auto()
        REGISTER = auto()

    class _Sids(Enum):
        FROM_SELF = auto()
        FROM_ARG = auto()
        NONE = auto()  # Don't use sids.

    def __init__(self, sids=None, base_url=Links.BASE_URL):
        import requests

        self._urls = {
            self._MethodGroup.REGISTER: Links.cgi_bin(base_url) + '/register',
            self._MethodGroup.CLIENT: Links.contest_root(base_url),
        }

        self._http = requests.Session()
        self._http.headers = {'User-Agent': f'kokos/{__version__}'}

        # For @_api_method's
        self._params = {}
        self._data = {}
        self._files = {}

        self._sids = sids

    def _request(self, method, url, need_json, **kwargs):
        resp = method(url, **kwargs)
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

    # @staticmethod  # Cannot be used as decorator in python < 3.10 (bpo-43682)
    def _api_method(
            http_method: _Http,
            method_group: _MethodGroup,
            action: str,
            *,
            sids: _Sids = _Sids.FROM_SELF,
            need_json: bool = True,
            files: Sequence[str] = (),
            ignore: Sequence[str] = (),
    ):
        """Wrapper for API methods.

        Args:
            http_method: GET/POST.
            method_group: Determines URL for the request.
            action: Action name, passed in 'action' parameter of URL.
            sids: Which sids to use for auth:
            need_json: Whether to parse the response or not. Errors are always parsed.
            files: Names of args which will be passed as files to requests.post.
                Must be used only for POST methods.
                Must not intersect with `ignore` or contain 'sids'.
            ignore: Names of args which shouldn't be added to _params or _data.
                Must not intersect with `files` or contain 'sids'.

        API methods should be declared like this:
        @_api_method(...)
        def method_name(self, ...):
            ...  # Change _params, _data and _files, if needed.

        For GET methods, all args are passed in params.
        For POST methods, all args are passed in request body.
        You can (but probably shouldn't) move some args from params (self._params)
        to body (self._data), or vice versa, for POST requests.
        """

        def decorator(method):

            @wraps(method)
            def wrapper(*args, **kwargs):
                # Get actual args for method call.
                self: BaseAPI = args[0]
                bound_arguments = inspect.signature(method).bind(*args, **kwargs)
                bound_arguments.apply_defaults()
                method_args = bound_arguments.arguments
                original_args = method_args.copy()
                method_args.pop('self')

                self._files.clear()
                for name in files:
                    self._files[name] = method_args.pop(name)
                for name in ignore:
                    method_args.pop(name)

                data = {'action': action, 'json': 1}  # need json reply where it's supported.
                req_sids = None
                if sids is self._Sids.FROM_SELF:
                    req_sids = self._sids
                elif sids is self._Sids.FROM_ARG:
                    req_sids = method_args.pop('sids')
                if req_sids is not None:
                    data.update(req_sids.as_dict())
                data.update(method_args)

                if http_method is self._Http.GET:
                    self._params = data
                    # _data shouldn't be used
                elif http_method is self._Http.POST:
                    self._params.clear()  # method may modify _params.
                    self._data = data
                else:
                    assert False

                # Modify _params/_data/_files if needed.
                method(**original_args)

                url = self._urls[method_group]
                if http_method is self._Http.GET:
                    return self._request(self._http.get, url, need_json, params=self._params)
                elif http_method is self._Http.POST:
                    return self._request(
                        self._http.post, url, need_json,
                        params=self._params, data=self._data, files=self._files
                    )
                else:
                    assert False

            return wrapper

        return decorator


class API(BaseAPI):
    """Unprivileged API methods."""

    _Http = BaseAPI._Http  # For short declarations. Is there a better way?
    _MethodGroup = BaseAPI._MethodGroup
    _Sids = BaseAPI._Sids
    _api_method = BaseAPI._api_method

    @_api_method(_Http.POST, _MethodGroup.REGISTER, 'login-json', sids=_Sids.NONE)
    def login(self, login: str, password: str):
        """get sids for enter_contest method"""
        pass

    @_api_method(_Http.POST, _MethodGroup.REGISTER, 'enter-contest-json', sids=_Sids.FROM_ARG)
    def enter_contest(self, sids: Sids, contest_id: int):
        pass

    @_api_method(_Http.GET, _MethodGroup.CLIENT, 'contest-status-json')
    def contest_status(self):
        pass

    @_api_method(_Http.GET, _MethodGroup.CLIENT, 'problem-status-json')
    def problem_status(self, problem: int):
        pass

    @_api_method(_Http.GET, _MethodGroup.CLIENT, 'problem-statement-json', need_json=False)
    def problem_statement(self, problem: int):
        pass

    @_api_method(_Http.GET, _MethodGroup.CLIENT, 'list-runs-json')
    def list_runs(self, prob_id: Optional[int] = None):
        # newest runs go first
        # If prob_id is None, then all runs are returned (useful for sync?)
        pass

    @_api_method(_Http.GET, _MethodGroup.CLIENT, 'run-status-json')
    def run_status(self, run_id: int):
        pass

    @_api_method(_Http.GET, _MethodGroup.CLIENT, 'download-run', need_json=False)
    def download_run(self, run_id: int):
        pass

    @_api_method(_Http.GET, _MethodGroup.CLIENT, 'run-messages-json')
    def run_messages(self, run_id: int):
        pass

    # run-test-json - test results? unknown params

    @_api_method(_Http.POST, _MethodGroup.CLIENT, 'submit-run', files=['file'], ignore=['lang'])
    def submit(
            self,
            prob_id: int,
            file: Union[Path, Tuple[str, BinaryIO]],
            lang: Union[Lang, int, None],
    ):
        # NOTE if lang is not None, this method may possibly break on output-only problems
        #      (see sm01-3 from 2020-2021)
        if isinstance(lang, Lang):
            self._data['lang_id'] = lang.value
        elif isinstance(lang, int):
            self._data['lang_id'] = lang
        # None will be ignored by requests
        if isinstance(file, Path):
            self._files['file'] = (file.name, open(file, 'rb'))

    def auth(self, creds: AuthData):
        """Get new sids.

        creds.judge is ignored. The API wrapper will use (un)privileged login based on its type.
        """
        # NOTE is 1step auth possible?
        top_level_sids = Sids.from_dict(self.login(creds.login, creds.password))
        self._sids = Sids.from_dict(self.enter_contest(top_level_sids, creds.contest_id))


class JudgeAPI(BaseAPI):
    """Privileged API methods.

    (Re)auth can be done only via EjudgeSession.
    """
    # TODO add token-based auth if it's implemented for privileged users.

    _Http = BaseAPI._Http  # For short declarations. Is there a better way?
    _MethodGroup = BaseAPI._MethodGroup
    _Sids = BaseAPI._Sids
    _api_method = BaseAPI._api_method

    def __init__(self, sids=None, base_url=Links.BASE_URL):
        super().__init__(sids, base_url)
        self._urls[self._MethodGroup.CLIENT] = Links.judge_root(base_url)

    @_api_method(_Http.GET, _MethodGroup.CLIENT, 'contest-status-json')
    def contest_status(self):
        pass

    # This should be a GET method, but filter can be too long to fit into URL.
    @_api_method(_Http.POST, _MethodGroup.CLIENT, 'list-runs-json')
    def list_runs(
            self,
            filter_expr: Optional[str] = None,
            first_run: Optional[int] = None,
            last_run: Optional[int] = None,
            field_mask: RunField = RunField.DEFAULT,
    ):
        """Get a (filtered) list of runs.

        The list of submissions is filtered (if filter is present),
        then first_run and last_run are used to return a slice of the result.

        Args:
            session: Ejudge session.
            filter_expr: Optional submission filter.
            first_run: First index of the slice.
            last_run: Last index of the slice (inclusive).
            field_mask: Which fields to include in the response. run_id is always present.

        Some notes on slice indices:
        - The slice is applied AFTER the filter.
        - If the first index is higher than the second,
          runs are returned in reverse chronological order.
        - Indices may be negative (like in Python)
        - If the first index is not specified, -1 is used
        - If the last index is not specified, at most 20 runs are returned
          (`first_run` is treated as the last index,
          runs are returned in reverse chronological order).
          If `first_run` is greater than the number of matches,
          ejudge will return less than 20 runs (bug/feature?).
        - If both indices are not set, last 20 runs are returned.
        For more details, see ejudge source code
        (lib/new_server_html_2.c:257-293 (at 773a153b1), lib/new_server_html.c:8602 (@c4c0ebb63))
        """
        self._data['field_mask'] = field_mask.value

    @_api_method(_Http.GET, _MethodGroup.CLIENT, 'run-status-json')
    def run_status(self, run_id: Optional[int] = None, run_uuid: Optional[str] = None):
        if run_id is None and run_uuid is None:
            raise ValueError('Either run_id or run_uuid should be provided.')
        if run_id is not None and run_uuid is not None:
            raise ValueError('run_id and run_uuid parameters are mutually exclusive.')

    @_api_method(_Http.GET, _MethodGroup.CLIENT, 'download-run', need_json=False)
    def download_run(self, run_id: int):
        pass


# TODO add params to Page members? PAGE_NAME = (page_id, avail_for_regular_users, avail_for_judges)
_judge_pages = [
    Page.MAIN_PAGE,
    # Page.USER_STANDINGS,  # standings format for judges is different
    Page.VIEW_SOURCE,
    Page.DOWNLOAD_SOURCE,
    Page.SET_RUN_STATUS,
    Page.USERS_AJAX,
    Page.SEND_COMMENT,
    Page.IGNORE_WITH_COMMENT,
    Page.OK_WITH_COMMENT,
    Page.REJECT_WITH_COMMENT,
    Page.SUMMON_WITH_COMMENT,
    Page.CHANGE_RUN_PROB_ID,
    Page.CHANGE_RUN_LANGUAGE,
    Page.CHANGE_RUN_SCORE,
    Page.CHANGE_RUN_SCORE_ADJ,
    Page.EDIT_RUN,
    Page.EDIT_RUN_FORM,
    Page.REJUDGE_DISPLAYED_CONFIRM,
    Page.REJUDGE_PROBLEM_CONFIRM,
    Page.REJUDGE_DISPLAYED,
    Page.REJUDGE_PROBLEM,
    Page.DOWNLOAD_ARCHIVE,
    Page.DOWNLOAD_ARCHIVE_FORM,
    Page.CLEAR_DISPLAYED,
    Page.CLEAR_DISPLAYED_CONFIRM,
]


class EjudgeSession:

    @dataclass(frozen=True)
    class _SessionKey:
        base_url: str
        contest_id: int
        login: str
        judge: bool

        @classmethod
        def create(cls, base_url: str, auth_data: AuthData):
            return cls(base_url, auth_data.contest_id, auth_data.login, auth_data.judge)

    def __init__(
            self, *,
            auth: bool = True,
            auth_data: Optional[AuthData] = None,
            base_url: str = Links.BASE_URL,
            storage_path: str = 'sessions-judge',
            quiet: bool = False,
    ):
        """
        Args:
            auth: if True and stored auth state is not found, call auth() after initialization.
            auth_data: Optional auth data. If not provided, auth data will be loaded from config.
                The session stores a copy of auth data,
                i.e. changes made to the original auth_data don't propagate to the session.
            base_url: Ejudge URL in "scheme://host[:port]" format.
            storage_path: path to storage file for auth state.
                Path should be relative to kks config dir or absolute.
            quiet: If True, don't show internal (re)auth attempts. Useful for scripts.
        """
        import requests
        self._http = requests.Session()

        self.quiet = quiet

        if auth_data is not None:
            self._auth_data = copy(auth_data)
        else:
            self._auth_data = AuthData.load_from_config()  # Can be None
        self._sids = Sids(None, None)

        self._base_url = base_url
        self._update_contest_root()

        self._storage = PickleStorage(storage_path, compress=True)
        self._load_auth_state()

        if self._sids.sid and self._sids.ejsid:
            self._http.cookies.set('EJSID', self._sids.ejsid, domain=urlsplit(self._base_url).netloc)
        elif auth:
            self._auth()

    def auth(self, auth_data: Optional[AuthData] = None):
        """
        Args:
            auth_data: If present, its copy will be used to replace the session's AuthData.
        """
        self._auth(auth_data, internal=False)

    def _auth(self, auth_data: Optional[AuthData] = None, internal: bool = True):
        if internal and not self.quiet:
            click.secho(
                'Ejudge session is missing or invalid, trying to auth with saved data',
                fg='yellow', err=True
            )

        if auth_data is not None:
            self._auth_data = copy(auth_data)
        if self._auth_data is None:
            raise AuthError(
                'Auth data is not found, please use "kks auth" to log in', fg='yellow'
            )

        if self._auth_data.password is None:
            # TODO Better prompt for session.auth(auth_data)?
            self._auth_data.password = click.prompt('Password', hide_input=True)

        import requests

        self._http.cookies.clear()
        url = Links.contest_login(self._auth_data, self._base_url)
        page = self._http.post(url, data={
            'login': self._auth_data.login,
            'password': self._auth_data.password,
        })

        if page.status_code != requests.codes.ok:
            raise AuthError(f'Failed to authenticate (status code {page.status_code})')

        if 'Invalid contest' in page.text or 'invalid contest_id' in page.text:
            raise AuthError(f'Invalid contest (contest id {self._auth_data.contest_id})')

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
        if self.judge:
            return JudgeAPI(self._sids, base_url=self._base_url)
        return API(self._sids, base_url=self._base_url)

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
                self._auth()
                return api_method(*args, **kwargs)
            raise e

    @staticmethod
    def needs_auth(url):
        return 'SID' in parse_qs(urlsplit(url).query)

    @property
    def base_url(self):
        return self._base_url

    @property
    def judge(self):
        if self._auth_data is None:
            return False  # No saved auth data
        return self._auth_data.judge

    def _update_sids(self, url):
        self._sids.sid = parse_qs(urlsplit(url).query)['SID'][0]
        self._sids.ejsid = self._http.cookies['EJSID']

    def _store_auth_state(self):
        assert self._auth_data is not None
        key = self._SessionKey.create(self._base_url, self._auth_data)
        with self._storage.load() as storage:
            storage.set(key, self._sids)

    def _load_auth_state(self):
        if self._auth_data is None:
            return
        key = self._SessionKey.create(self._base_url, self._auth_data)
        with self._storage.load() as storage:
            cached_sids = storage.get(key)
        if cached_sids is not None:
            self._sids = cached_sids

    def _check_page_access(self, page_id: Page):
        if self.judge:
            if page_id not in _judge_pages:
                raise EjudgeError('Page is not available for judges')
        else:
            pass

    def _update_contest_root(self):
        # Cache the url to avoid rebuilding it for each request
        self._contest_root = Links.contest_root(self._base_url, judge=self.judge)

    def _request(self, method, url, *args, **kwargs):
        # NOTE params should only be passed as a keyword argument
        params = kwargs.get('params', {}).copy()
        # If SID is included in the url, remove it to avoid conflict with session's SID in params
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        if 'SID' in query:
            query.pop('SID')
            url = parts._replace(query=urlencode(query, doseq=True)).geturl()
        params['SID'] = self._sids.sid
        page_id: Optional[Page] = kwargs.pop('page_id', None)
        if page_id is not None:
            params['action'] = page_id.value
        kwargs['params'] = params

        response = method(url, *args, **kwargs)
        _check_response(response)
        # the requested page may contain binary data (e.g. problem attachments)
        if b'Invalid session' in response.content:
            self._auth()
            params['SID'] = self._sids.sid
            response = method(url, *args, **kwargs)
        return response

    def get(self, url, *args, **kwargs):
        if args:
            kwargs['params'] = args[0]
            args = args[1:]
        return self._request(self._http.get, url, *args, **kwargs)

    def post(self, url, *args, **kwargs):
        return self._request(self._http.post, url, *args, **kwargs)

    def get_page(self, page_id: Page, *args, **kwargs):
        self._check_page_access(page_id)
        return self.get(self._contest_root, *args, page_id=page_id, **kwargs)

    def post_page(self, page_id: Page, *args, **kwargs):
        self._check_page_access(page_id)
        return self.post(self._contest_root, *args, page_id=page_id, **kwargs)
