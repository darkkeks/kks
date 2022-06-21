from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from enum import Enum, Flag
from functools import wraps
from typing import BinaryIO, Iterable, Optional

from kks.ejudge import MSK_TZ, PROBLEM_INFO_VERSION, \
    BaseSubmission, Lang, Page, ParsedRow, _CellParsers, _FieldParsers, \
    _parse_field, _skip_field, get_server_tz
# move parsers and fields into utils module?
from kks.errors import EjudgeError
from kks.util.storage import Cache, PickleStorage


def requires_judge(func):
    @wraps(func)
    def wrapper(session, *args, **kwargs):
        if not session.judge:
            raise EjudgeError('Method is only available for judges')
        return func(session, *args, **kwargs)
    return wrapper


class ClarFilter(Enum):
    ALL = 1
    UNANSWERED = 2
    ALL_WITH_COMMENTS = 3
    TO_ALL = 4


@dataclass(frozen=True)
class Submission(BaseSubmission):
    user: str = field(init=False)  # Not in order

    def __post_init__(self):
        object.__setattr__(self, 'user', self.size_or_user)

    def set_status(self, session, status: int):
        # how to check success?
        session.post_page(Page.SET_RUN_STATUS, {'run_id': self.id, 'status': status})

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

    def send_comment(self, session, comment: str, status: Optional[int] = None):
        from kks.util.ejudge import RunStatus

        if status == RunStatus.IGNORED:
            page = Page.IGNORE_WITH_COMMENT
        elif status == RunStatus.OK:
            page = Page.OK_WITH_COMMENT
        elif status == RunStatus.REJECTED:
            page = Page.REJECT_WITH_COMMENT
        elif status == RunStatus.SUMMONED:
            page = Page.SUMMON_WITH_COMMENT
        elif status is None:
            page = Page.SEND_COMMENT
        else:
            raise ValueError(f'Unsupported status: {status}')  # TODO use enum for status

        session.post_page(page, {'run_id': self.id, 'msg_text': comment})  # how to check success?


@dataclass(frozen=True)
class ClarInfo(ParsedRow):
    id: int
    # Possible values: "", "N" - unanswered?, "A" - answered?, "R" - not used?
    flags: str = _parse_field(_CellParsers.clar_flags)
    # NOTE other time formats? (show_astr_time in lib/new_server_html_2.c:ns_write_all_clars)
    time: datetime = _parse_field(_CellParsers.clar_time)
    ip: str
    size: int
    from_user: str
    to: str
    subject: str
    details: str = _parse_field(_CellParsers.clar_details)

    @classmethod
    def parse(cls, row, server_tz=timezone.utc):
        attrs = cls._parse(row)
        attrs['time'] = attrs['time'].replace(tzinfo=server_tz).astimezone(MSK_TZ)
        return cls(**attrs)


def _dict_skip_field(key=None, parser=None):
    meta = {'skip': True}
    if key is not None:
        meta['key'] = key
    if parser is not None:
        meta['parser'] = parser
    return field(init=False, repr=False, compare=False, metadata=meta)


def _dict_parse_field(key, parser=None):
    return field(metadata={'key': key, 'parser': parser})


@dataclass(frozen=True)
class User:
    """Subset of user info from "Regular users" page."""
    serial: int = _dict_skip_field()  # row number in the rendered table (?)
    id: int = _dict_parse_field('user_id')
    login: str = _dict_parse_field('user_login')
    name: str = _dict_parse_field('user_name', _FieldParsers.parse_bad_encoding)
    is_banned: bool
    is_invisible: bool
    is_locked: bool  # ?
    is_incomplete: bool  # ?
    is_disqualified: bool  # != is_banned?
    is_privileged: bool
    is_reg_readonly: bool
    # NOTE timestamps are not parsed. If you wish to add them to the class,
    #      you will need to pass timezone info to `parse` (see ClarInfo for an example).
    registration_date: datetime = _dict_skip_field('create_time', _FieldParsers.parse_optional_datetime)
    login_date: datetime = _dict_skip_field('last_login_time', _FieldParsers.parse_optional_datetime)
    run_count: int
    run_size: int
    clar_count: int
    result_score: int = _skip_field()  # ?

    # move to a separate base class?
    @classmethod
    def parse(cls, data):

        def parse_field(field):
            key = field.metadata.get('key', field.name)
            parser = field.metadata.get('parser')
            if not parser:
                # NOTE will not work with Optional types
                return field.type(data[key])
            return parser(data[key])

        attrs = {
            field.name: parse_field(field)
            for field in fields(cls) if field.init
        }
        return cls(**attrs)


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
    use_problem_extid: bool = False # Use 'extid' as problem name (extid is some kind of id for ej-batch)
    use_problem_dir: bool = False  # Use 'problem_dir' as problem name (ejudge uses true by default)
    problem_dir_prefix: str = ''  # Common prefix to remove
    runs_or_ids: Iterable = ()  # used only if run_selection is SELECTED


def _need_filter_reset(old_filter_status: Iterable[bool], new_filter_status: Iterable[bool]):
    # filter status[i] = ith component is not empty
    return any(
        new_status < old_status
        for (old_status, new_status) in zip(old_filter_status, new_filter_status)
    )


def _run_mask(runs_or_ids: Optional[Iterable]):
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
def ejudge_submissions(session, filter_=None, first_run=None, last_run=None):
    """Parses (filtered) submissions table.

    The list of submissions is filtered,
    then first_run and last_run are used to return a slice of the result.
    Filtering and slicing are done on the server side.

    Args:
        session: Ejudge session.
        filter_: Optional submission filter.
        first_run: First index of the slice.
        last_run: Last index of the slice (inclusive).

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
    (lib/new_server_html_2.c:257-293 (at 773a153b1))
    """
    # TODO use JSON?
    # ejudge has a `priv_list_runs_json` method (action id 301, same as for unprivileged users).
    # If this page is requested from a regular session, main page is returned for some reason.
    from bs4 import BeautifulSoup

    filter_status = (bool(filter_), first_run is not None, last_run is not None)
    storage = PickleStorage('storage')
    with storage.load():
        old_filter_status = storage.get('last_filter_status', (False, False, False))

    page = None
    # A reset is required even if one field is reset (WTF)
    if _need_filter_reset(old_filter_status, filter_status):
        page = session.get_page(
            Page.MAIN_PAGE,
            params={'action_65': 'Reset filter'}
        )
    with storage.load():
        storage.set('last_filter_status', filter_status)

    # page is None <=> no filters, a reset was performed last time
    if any(filter_status) or page is None:
        page = session.get_page(
            Page.MAIN_PAGE,
            params={
                'filter_expr': filter_,
                'filter_first_run': first_run,
                'filter_last_run': last_run
            }
        )
    soup = BeautifulSoup(page.content, 'html.parser')
    title = soup.find('h2', text='Submissions')
    table = title.find_next('table', {'class': 'b1'})
    if table is None or table.find_previous('h2') is not title:
        # Bad filter expression (other errors?)
        return None
    with Cache('problem_info', compress=True, version=PROBLEM_INFO_VERSION).load() as cache:
        server_tz = get_server_tz(cache, session)
    return [Submission.parse(row, server_tz) for row in table.find_all('tr')[1:]]


@requires_judge
def ejudge_clars(session, filter_=ClarFilter.UNANSWERED, first_clar=None, last_clar=None):
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
    title = soup.find('h2', text='Messages')
    table = title.find_next('table', {'class': 'b1'})
    if table is None or table.find_previous('h2') is not title:
        return None  # is this possible?
    return [ClarInfo.parse(row) for row in table.find_all('tr')[1:]]


@requires_judge
def ejudge_users(session, show_not_ok=False, show_invisible=False, show_banned=False, show_only_pending=False):
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
    }).json()
    if 'data' not in resp:
        return []  # TODO handle errors?
    return [User.parse(user) for user in resp['data']]


# Inconsistent naming, but it's more readable than ejudge_rejudge or something similar
@requires_judge
def rejudge_runs(session, runs_or_ids: Iterable):
    resp = session.post_page(Page.REJUDGE_DISPLAYED, _run_mask(runs_or_ids))
    # TODO check status


@requires_judge
def ejudge_archive(session, settings: ArchiveSettings, output: BinaryIO):
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