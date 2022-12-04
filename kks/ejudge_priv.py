from dataclasses import dataclass, field, fields, Field
from datetime import datetime, timezone
from enum import Enum, Flag
from functools import wraps
from typing import BinaryIO, Iterable, List, Optional, Union
from urllib.parse import urlencode

from kks.ejudge import MSK_TZ, PROBLEM_INFO_VERSION, \
    BaseSubmission, TableRowDataclass, _CellParsers, _FieldParsers, \
    _skip_field, get_server_tz
# move parsers and fields into utils module?
from kks.errors import EjudgeError
from kks.util.ejudge import EjudgeSession, JudgeAPI, Lang, Links, Page, RunField, RunStatus
from kks.util.storage import Cache, PickleStorage


RunsOrIds = Iterable[Union[int, BaseSubmission]]


def requires_judge(func):
    @wraps(func)
    def wrapper(session, *args, **kwargs):
        if not session.judge:
            raise EjudgeError('Method is only available for judges')
        return func(session, *args, **kwargs)
    return wrapper


class JSONDataclass:  # TODO modify @dataclass?
    """Base for dataclasses which can be parsed from JSON."""
    @staticmethod
    def _field(*, key=None, parser=None):
        return field(metadata={'key': key, 'parser': parser})

    @staticmethod
    def _optional_field(*, key=None, parser=None) -> Field:
        return field(default=None, metadata={'key': key, 'parser': parser})

    @staticmethod
    def _de_opt(type_):
        """Get argument of Optional."""
        # Using getattr, because typing.get_origin and get_args are available only in py3.8+
        # (3.7+ with typing-extensions)

        # Optional[T] = Union[T, None]
        if getattr(type_, '__origin__', None) is not Union:
            return type_
        args = getattr(type_, '__args__', ())
        assert len(args) == 2 and type(None) in args, "Cannot parse generic `Union`s without custom parser"
        if args[0] is type(None):
            return args[1]
        return args[0]

    @classmethod
    def _init_field_types(cls):
        # Hack to speed up optional field parsing.
        if getattr(cls, '_real_types', None):
            return
        real_types = {}
        for field in fields(cls):
            if field.init:
                real_types[field.name] = cls._de_opt(field.type)
        cls._real_types = real_types

    @classmethod
    def parse(cls, data, *args, **kwargs):
        cls._init_field_types()  # TODO move to metaclass?
        attrs = cls._parse(data, *args, **kwargs)
        return cls(**attrs)

    @classmethod
    def _parse(cls, data):

        def parse_field(field):
            key = field.metadata.get('key') or field.name
            value = data.get(key)
            if value is None:
                return None

            parser = field.metadata.get('parser')
            if not parser:
                return cls._real_types[field.name](value)
            return parser(value)

        attrs = {
            field.name: parse_field(field)
            for field in fields(cls) if field.init
        }
        return attrs


class ClarFilter(Enum):
    ALL = 1
    UNANSWERED = 2
    ALL_WITH_COMMENTS = 3
    TO_ALL = 4


@dataclass(frozen=True)
class Submission(JSONDataclass, BaseSubmission):
    _field = JSONDataclass._field
    _optional_field = JSONDataclass._optional_field

    id: int = _field(key='run_id')
    uuid: Optional[str] = _optional_field(key='run_uuid')
    sha1: Optional[str] = None

    status: Optional[RunStatus] = None
    status_str: Optional[str] = None  # 2-letter status, like in filter

    time: Optional[datetime] = _optional_field(key='run_time', parser=datetime.fromtimestamp)
    nsec: Optional[int] = None  # Nanoseconds part of `time`
    time_us: Optional[datetime] = _optional_field(key='run_time_us', parser=lambda ts: datetime.fromtimestamp(ts/10**6))
    rel_time: Optional[int] = _optional_field(key='duration')  # Seconds from start of contest.

    eoln_type: Optional[int] = None  # Some enum

    user_name: Optional[str] = None
    user_id: Optional[int] = None
    user_login: Optional[str] = None

    prob_id: Optional[int] = None
    problem: Optional[str] = _optional_field(key='prob_name')

    compiler: Optional[Lang] = _optional_field(key='lang_id')
    compiler_name: Optional[str] = _optional_field(key='lang_name')

    ip: Optional[str] = None
    ssl: Optional[bool] = None

    size: Optional[int] = None
    store_flags: Optional[int] = None  # ?

    tests_passed: Optional[int] = _optional_field(key='raw_test')
    # Ejudge sets "failed_test" or "tests_passed" field based on mode.
    # In Kirov scoring system (used in CAOS course) raw_test is always equal to tests_passed.
    passed_mode: Optional[int] = _skip_field()

    raw_score: Optional[int] = None  # Without penalties
    score: Optional[int] = None  # With penalties
    score_str: Optional[str] = None  # "50=100-50", "99=100-1*1", etc.

    base_url: str = Links.BASE_URL
    source_details: Optional[str] = field(init=False, default=None)
    source: Optional[str] = field(init=False, default=None)
    report: Optional[str] = field(init=False, default=None)

    def set_status(self, session, status: RunStatus):
        # how to check success?
        session.post_page(Page.SET_RUN_STATUS, {'run_id': self.id, 'status': status.value})

    def set_lang(self, session, lang: Lang):
        # how to check success?
        session.post_page(Page.CHANGE_RUN_LANGUAGE, {'run_id': self.id, 'param': lang.value})
        # redirects to VIEW_SOURCE on success?

    def set_prob_id(self, session, prob_id: int):
        session.post_page(Page.CHANGE_RUN_PROB_ID, {'run_id': self.id, 'param': prob_id})

    def set_score(self, session, score: int):
        session.post_page(Page.CHANGE_RUN_SCORE, {'run_id': self.id, 'param': score})

    def set_score_adj(self, session, score_adj: int):
        session.post_page(Page.CHANGE_RUN_SCORE_ADJ, {'run_id': self.id, 'param': score_adj})

    def send_comment(self, session, comment: str, status: Optional[RunStatus] = None):
        if status is RunStatus.IGNORED:
            page = Page.IGNORE_WITH_COMMENT
        elif status is RunStatus.OK:
            page = Page.OK_WITH_COMMENT
        elif status is RunStatus.REJECTED:
            page = Page.REJECT_WITH_COMMENT
        elif status is RunStatus.SUMMONED:
            page = Page.SUMMON_WITH_COMMENT
        elif status is None:
            page = Page.SEND_COMMENT
        else:
            raise ValueError(f'Unsupported status: {status}')  # TODO use enum for status

        session.post_page(page, {'run_id': self.id, 'msg_text': comment})  # how to check success?

    @classmethod
    def _parse(cls, data, base_url=Links.BASE_URL):
        attrs = super()._parse(data)
        attrs['base_url'] = base_url
        return attrs

    def _set_link(self, attr: str, page: Page):
        link = (
            Links.judge_root(self.base_url) + '?' +
            urlencode({'action': page.value, 'run_id': self.id})
        )
        object.__setattr__(self, attr, link)

    def __post_init__(self):
        if self.status is RunStatus.EMPTY:
            return

        self._set_link('source_details', Page.VIEW_SOURCE)
        self._set_link('source', Page.DOWNLOAD_SOURCE)
        if self.status is not RunStatus.IGNORED:
            # Ejudge keeps reports for ignored runs, but doesn't allow to see them
            self._set_link('report', Page.VIEW_REPORT)

    @property
    def user(self):
        return self.user_name or self.user_login


@dataclass(frozen=True)
class ClarInfo(TableRowDataclass):
    _field = TableRowDataclass._field

    id: int
    # Possible values:
    # For judge/admin: "", "N" - unanswered?, "A" - answered?, "R" - not used?
    # Unprivileged user: "U" - unanswered, "A" - answered, "N" - ?
    flags: str = _field(_CellParsers.clar_flags)
    # NOTE other time formats? (show_astr_time in lib/new_server_html_2.c:ns_write_all_clars)
    time: datetime = _field(_CellParsers.clar_time)
    ip: str
    size: int
    from_user: str
    to: str
    subject: str
    details: str = _field(_CellParsers.clar_details)

    @classmethod
    def _parse(cls, row, server_tz=timezone.utc):
        attrs = super()._parse(row)
        attrs['time'] = attrs['time'].replace(tzinfo=server_tz).astimezone(MSK_TZ)
        return attrs


@dataclass(frozen=True)
class User(JSONDataclass):
    """Subset of user info from "Regular users" page."""

    _field = JSONDataclass._field

    serial: int = _skip_field()  # row number in the rendered table (?)
    id: int = _field(key='user_id')
    login: str = _field(key='user_login')
    name: str = _field(key='user_name')
    is_banned: bool
    is_invisible: bool
    is_locked: bool  # ?
    is_incomplete: bool  # ?
    is_disqualified: bool  # not the same as is_banned?
    is_privileged: bool
    is_reg_readonly: bool
    registration_date: datetime = _field(key='create_time', parser=_FieldParsers.parse_optional_datetime)
    login_date: Optional[datetime] = _field(key='last_login_time', parser=_FieldParsers.parse_optional_datetime)
    run_count: int
    run_size: int
    clar_count: int
    result_score: int = _skip_field()  # ?

    @classmethod
    def _parse(cls, data, server_tz=timezone.utc):
        attrs = super()._parse(data)
        attrs['registration_date'] = attrs['registration_date'].replace(tzinfo=server_tz).astimezone(MSK_TZ)
        if attrs['login_date'] is not None:
            attrs['login_date'] = attrs['login_date'].replace(tzinfo=server_tz).astimezone(MSK_TZ)
        return attrs


@dataclass
class ArchiveSettings:
    class RunSelection(Enum):
        ALL = 0
        SELECTED = 1
        OK = 2
        OK_PR = 3
        OK_PR_RJ_IG_PD_DQ = 4

    class FilePattern(Flag):
        def __new__(cls, param_name):
            obj = object.__new__(cls)
            obj._value_ = 1 << len(cls.__members__)
            obj.param_name = param_name
            return obj

        CONTEST_ID = 'file_pattern_contest'
        RUN_ID = 'file_pattern_run'
        USER_ID = 'file_pattern_uid'
        USER_LOGIN = 'file_pattern_login'
        USER_NAME = 'file_pattern_name'
        PROBLEM_SHORT_NAME = 'file_pattern_prob'
        LANG_SHORT_NAME = 'file_pattern_lang'
        SUBMIT_TIME = 'file_pattern_time'
        LANG_SUFFIX = 'file_pattern_suffix'

    class DirStruct(Enum):
        NONE = 0
        PROBLEM = 1
        USER_ID = 2
        USER_LOGIN = 3
        USER_NAME = 8
        PROBLEM_USER_ID = 4
        PROBLEM_USER_LOGIN = 5
        PROBLEM_USER_NAME = 9
        USER_ID_PROBLEM = 6
        USER_LOGIN_PROBLEM = 7
        USER_NAME_PROBLEM = 10

    run_selection: RunSelection = RunSelection.OK_PR_RJ_IG_PD_DQ
    file_pattern: FilePattern = (FilePattern.CONTEST_ID | FilePattern.RUN_ID
                                | FilePattern.USER_NAME | FilePattern.SUBMIT_TIME
                                | FilePattern.LANG_SUFFIX)
    dir_struct: DirStruct = DirStruct.PROBLEM
    use_problem_extid: bool = False  # Use 'extid' as problem name (extid is some kind of id for ej-batch)
    use_problem_dir: bool = False  # Use 'problem_dir' as problem name (ejudge uses true by default)
    problem_dir_prefix: str = ''  # Common prefix to remove
    runs_or_ids: RunsOrIds = ()  # used only if run_selection is SELECTED


def _need_filter_reset(old_filter_status: Iterable[bool], new_filter_status: Iterable[bool]):
    # filter status[i] = ith component is not empty
    return any(
        new_status < old_status
        for (old_status, new_status) in zip(old_filter_status, new_filter_status)
    )


def _run_mask(runs_or_ids: RunsOrIds):
    # binmask = sum(1 << run_id for run_id in ids)
    # run_mask = f'{binmask & UINT64_MAX:x}+{(binmask >> 64) & UINT64_MAX:x}+...'
    mask = []
    if runs_or_ids is not None:
        for run_id in sorted(x.id if isinstance(x, BaseSubmission) else x for x in runs_or_ids):
            chunk = run_id // 64
            while len(mask) <= chunk:
                mask.append(0)
            mask[-1] += 1 << (run_id % 64)
    return {
        'run_mask_size': len(mask),
        'run_mask': '+'.join(f'{chunk:x}' for chunk in mask),
    }


@requires_judge
def ejudge_submissions(
        session: EjudgeSession,
        filter_: Optional[str] = None,
        first_run: Optional[int] = None,
        last_run: Optional[int] = None,
        field_mask: RunField = RunField.DEFAULT | RunField.USER_LOGIN,  # always non-empty .user
    ) -> List[Submission]:
    """Parses (filtered) submissions table.

    The list of submissions is filtered,
    then first_run and last_run are used to return a slice of the result.
    Filtering and slicing are done on the server side.

    Args:
        session: Ejudge session.
        filter_: Optional submission filter.
        first_run: First index of the slice.
        last_run: Last index of the slice (inclusive).
        field_mask: Which fields to include in the response. run_id is always present.

    See JudgeAPI.list_runs for more details.
    """

    api: JudgeAPI = session.api()
    submissions = session.with_auth(api.list_runs, filter_, first_run, last_run, field_mask)['runs']
    return [Submission.parse(sub, session.base_url) for sub in submissions]


@requires_judge
def ejudge_clars(
        session: EjudgeSession,
        filter_: ClarFilter = ClarFilter.UNANSWERED,
        first_clar: Optional[int] = None,
        last_clar: Optional[int] = None,
) -> Optional[List[ClarInfo]]:
    """Parses the list of clars.

    NOTE: first_clar and last_clar do not work as expected, see details below.

    Args:
        filter_: Which clars to return.
        first_clar: First index in the *unfiltered* list of clars Default: -1.
        last_clar: How many clars to return (see below). Default: -10.

    From ejudge source:
    > last_clar is actually count
    > count == 0, show all matching in descending border
    > count < 0, descending order
    > count > 0, ascending order

    first_clar (last_clar) must be in range [-total, total-1],
    where "total" is the total number of clars (unfiltered).
    If value is not in the allowed range, -1 (-10) is used.
    """
    from bs4 import BeautifulSoup

    filter_status = (first_clar is not None, last_clar is not None)
    storage = PickleStorage('storage')
    with storage.load():
        old_filter_status = storage.get('last_clar_filter_status', (False, False))

    page = None
    # A reset is required even if one field is reset (?)
    if _need_filter_reset(old_filter_status, filter_status):
        page = session.get_page(
            Page.MAIN_PAGE,
            params={'action_73': 'Reset filter'}
        )
    with storage.load():
        storage.set('last_clar_filter_status', filter_status)

    # Use result from reset if indicess are not set and filter is UNANSWERED.
    if page is None or any(filter_status) or filter_ is not ClarFilter.UNANSWERED:
        page = session.get_page(
            Page.MAIN_PAGE,
            params={
                'filter_mode_clar': filter_.value,
                'filter_first_clar': first_clar,
                'filter_last_clar': last_clar
            }
        )

    soup = BeautifulSoup(page.content, 'html.parser')
    title = soup.find('h2', string='Messages')
    table = title.find_next('table', {'class': 'b1'})
    if table is None or table.find_previous('h2') is not title:
        return None  # is this possible?
    with Cache('problem_info', compress=True, version=PROBLEM_INFO_VERSION).load() as cache:
        server_tz = get_server_tz(cache, session)
    return [ClarInfo.parse(row, server_tz) for row in table.find_all('tr')[1:]]


@requires_judge
def ejudge_users(
        session: EjudgeSession,
        show_not_ok: bool = False,
        show_invisible: bool = False,
        show_banned: bool = False,
        show_only_pending: bool = False
) -> List[User]:
    """Gets users from the "Regular users" tab.

    Args:
        session: Ejudge session.
        show_not_ok: Include users with status(?) Pending/Rejected.
        show_invisible: Include users with the "invisible" flag.
        show_banned: Include banned/locked(?)/disqualified users.
        show_only_pending: Return only users with status Pending.
    """

    resp = session.get_page(Page.USERS_AJAX, {
        'show_not_ok': show_not_ok,
        'show_invisible': show_invisible,
        'show_banned': show_banned,
        'show_only_pending': show_only_pending,
    })
    resp.encoding = 'utf-8'  # see kks.util.ejudge.API
    resp = resp.json()
    if 'data' not in resp:
        return []  # TODO handle errors?

    with Cache('problem_info', compress=True, version=PROBLEM_INFO_VERSION).load() as cache:
        server_tz = get_server_tz(cache, session)
    return [User.parse(user, server_tz) for user in resp['data']]


# Inconsistent naming, but it's more readable than ejudge_rejudge or something similar
@requires_judge
def rejudge_runs(session: EjudgeSession, runs_or_ids: RunsOrIds) -> None:
    resp = session.post_page(Page.REJUDGE_DISPLAYED, _run_mask(runs_or_ids))
    # TODO check status


@requires_judge
def clear_runs(session: EjudgeSession, runs_or_ids: RunsOrIds) -> None:
    resp = session.post_page(Page.CLEAR_DISPLAYED, _run_mask(runs_or_ids))
    # TODO check status


@requires_judge
def ejudge_archive(session: EjudgeSession, settings: ArchiveSettings, output: BinaryIO) -> None:
    # TODO move params construction to ArchiveSettings method?
    params = {
        'run_selection': settings.run_selection.value,
        'dir_struct': settings.dir_struct.value,
        'problem_dir_prefix': settings.problem_dir_prefix,
    }
    if settings.use_problem_extid:
        params['use_problem_extid'] = 'on'
    if settings.use_problem_dir:
        params['use_problem_dir'] = 'on'
    for flag in ArchiveSettings.FilePattern:
        if flag in settings.file_pattern:
            params[flag.param_name] = 'on'
    # needed even if run_selection is not SELECTED
    params.update(_run_mask(settings.runs_or_ids))

    resp = session.post_page(Page.DOWNLOAD_ARCHIVE, params, stream=True)
    # TODO check status
    for chunk in resp.iter_content(1024**2):
        output.write(chunk)
