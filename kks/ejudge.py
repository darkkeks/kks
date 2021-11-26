import re
from copy import copy
from dataclasses import dataclass, field, fields
from datetime import datetime, timedelta, timezone
from enum import Enum
from itertools import groupby
from typing import Optional
from urllib.parse import parse_qs, urlsplit, quote as urlquote

# import requests  # we use lazy imports to improve load time for local commands
# from bs4 import BeautifulSoup
# from bs4.element import NavigableString
import click
from tqdm import tqdm

from kks.errors import APIError, ParseError
from kks.util.h2t import HTML2Text


CONTEST_ID_BY_GROUP = {}
CONTEST_ID_BY_GROUP.update({
    f'19{group}': 130 + group for group in range(1, 12)
})
CONTEST_ID_BY_GROUP.update({
    f'20{group}': int(f'20{group}') for group in range(1, 11)
})
CONTEST_ID_BY_GROUP['free'] = 2021

GROUP_ID_BY_CONTEST = {
    contest_id: group_id for group_id, contest_id in CONTEST_ID_BY_GROUP.items()
}


PROBLEM_INFO_VERSION = 3
TIME_FORMAT = '%Y/%m/%d %H:%M:%S'
MSK_TZ = timezone(timedelta(hours=3))


class Links:
    HOST = 'caos.myltsev.ru'
    CGI_BIN = f'https://{HOST}/cgi-bin'
    WEB_CLIENT_ROOT = f'{CGI_BIN}/new-client'


class Page(Enum):
    MAIN_PAGE = 2
    VIEW_SOURCE = 36
    DOWNLOAD_SOURCE = 91
    USER_STANDINGS = 94
    SUMMARY = 137
    SUBMISSIONS = 140
    SUBMIT_CLAR = 141
    CLARS = 142
    SETTINGS = 143


class Status:
    OK = 'OK'
    OK_AUTO = 'OK (auto)'  # only in summary
    REVIEW = 'Pending review'
    CHECK = 'Pending check'
    TESTING = 'Accepted for testing'
    REJECTED = 'Rejected'
    IGNORED = 'Ignored'
    PARTIAL = 'Partial solution'
    NOT_SUBMITTED = 'Not submitted'


class AuthData:
    def __init__(self, login, contest_id, password=None):
        self.login = login
        self.contest_id = contest_id
        self.password = password


class BaseProblem:
    def __init__(self, short_name, href):
        self.short_name = short_name
        self.href = href

    def contest(self):
        return extract_contest_name(self.short_name)

    def extract_id(self):
        # TODO store id and generate URL dynamically?
        return parse_qs(urlsplit(self.href).query)['prob_id'][0]


class SummaryProblem(BaseProblem):
    def __init__(self, short_name, name, href, status, tests_passed, score):
        super().__init__(short_name, href)
        self.name = name
        self.status = status
        self.tests_passed = tests_passed
        self.score = score


class Problem(SummaryProblem):
    def color(self):
        return 'green' if self.status in [Status.OK, Status.OK_AUTO] \
            else 'green' if self.status == Status.REVIEW \
            else 'white' if self.status == Status.NOT_SUBMITTED \
            else 'bright_yellow' if self.status == Status.CHECK \
            else 'bright_yellow' if self.status == Status.TESTING \
            else 'red'

    def bold(self):
        return self.status in [Status.OK, Status.OK_AUTO]

    def get_full(self, session):
        return FullProblem.load(self, session)


class ProblemWithDeadline:
    def __init__(self, problem, contest):
        self._problem = problem
        self._contest = contest

    def deadline_color(self):
        return self._contest.deadline_color()

    def deadline_string(self):
        if self._contest.past_deadline():
            return 'Past deadline'
        return self._contest.deadlines.to_str(self._contest.active_deadline())

    def __getattr__(self, name):
        if name in ['deadlines', 'past_deadline', 'deadline_is_close', 'active_deadline']:
            return getattr(self._contest, name)
        return getattr(self._problem, name)


class CacheKeys:
    problem_links = 'problem_links'
    full_scores = 'full'
    run_penalties = 'run'
    server_tz = 'server_tz'

    @staticmethod
    def penalty(contest):
        return f'p_{contest}'

    @staticmethod
    def deadline(contest):
        return f'dl_{contest}'


def _skip_field(parser=None):
    meta = {'skip': True}
    if parser is not None:
        meta['parser'] = parser
    return field(init=False, repr=False, compare=False, metadata=meta)


def _parse_field(parser):
    return field(metadata={'parser': parser})


class _CellParsers:
    @staticmethod
    def _parse_optional(cell) -> Optional[str]:
        text = cell.text.strip()
        if text and text != 'N/A':
            return text
        return None

    @staticmethod
    def submission_id(cell):
        return int(cell.text.rstrip('#'))

    @staticmethod
    def submission_time(cell):
        # NOTE timezone is not set
        return datetime.strptime(cell.text, TIME_FORMAT)

    @staticmethod
    def submission_tests(cell):
        value = _CellParsers._parse_optional(cell)
        return int(value) if value is not None else None

    @staticmethod
    def submission_score(cell):
        value = _CellParsers._parse_optional(cell)
        if value is None:
            return None
        return int(re.sub(r'=.*', '', value))  # score may include penalty

    @staticmethod
    def submission_source(cell):
        source_link = cell.find('a')['href']
        return source_link.replace(
            f'action={Page.VIEW_SOURCE.value}',
            f'action={Page.DOWNLOAD_SOURCE.value}'
        )

    @staticmethod
    def submission_report(cell):
        report_link = cell.find('a')
        return report_link['href'] if report_link is not None else None


@dataclass(frozen=True)
class Submission:
    id: int = _parse_field(_CellParsers.submission_id)
    # `_skip_field`s are unused, also parsing of these fields may be unstable
    time: datetime = _skip_field(parser=_CellParsers.submission_time)
    size: int = _skip_field()
    problem: str
    compiler: str
    status: str
    tests_passed: Optional[int] = _skip_field(parser=_CellParsers.submission_tests)
    score: Optional[int] = _skip_field(parser=_CellParsers.submission_score)
    source: str = _parse_field(_CellParsers.submission_source)
    report: Optional[str] = _parse_field(_CellParsers.submission_report)

    @classmethod
    def parse(cls, row):

        def parse_field(field, cell):
            # this function is  never called on `_skip_field`s
            parser = field.metadata.get('parser')
            if not parser:
                # NOTE will not work with Optional types
                return field.type(cell.text)
            return parser(cell)

        cells = row.find_all('td')
        data = {
            field.name: parse_field(field, cell)
            for field, cell in zip(fields(cls), cells) if field.init
        }
        return cls(**data)

    def short_status(self):
        if self.status == Status.REVIEW:
            return 'Pending'
        if self.status == Status.CHECK:
            return 'Check'
        if self.status == Status.TESTING:
            return 'Testing'
        if self.status == Status.PARTIAL:
            return 'Partial'
        return self.status

    def suffix(self):
        if self.compiler.startswith('gas'):
            return '.S'
        if '++' in self.compiler:
            return '.cpp'
        if self.compiler.startswith('make'):
            return '.tar'
        if self.compiler.startswith('gcc') or self.compiler.startswith('clang'):
            return '.c'
        return ''


class Report:
    def __init__(self, comments, tests):

        def comm_format(comments):
            for row in comments:
                author_cell, comment, *_ = row.find_all('td')
                author = next(line for line in author_cell.text.splitlines() if line)
                # if the comment contains newlines
                yield from (
                    f'Comment by {author}: {comment.text.strip()}\n'
                    .splitlines(keepends=True)
                )

        if comments:
            self.lines = list(comm_format(comments))
        else:
            self.lines = []

        failed_tests = []

        for test in tests:
            test_num, status, *_ = test.find_all('td')
            if status.text != Status.OK:
                failed_tests.append(f'{test_num.text} - {status.text}\n')

        if failed_tests:
            if comments:
                self.lines.append('\n')
            self.lines.append(f'Total tests: {len(tests)}\n')
            self.lines.append('Failed tests:\n')
            self.lines += failed_tests

    def as_comment(self):
        sep_lines = 3
        return ''.join('// ' + line for line in self.lines) + '\n' * sep_lines


class TaskScore:
    def __init__(self, contest: str, score: Optional[str], status: str):
        self.contest = contest
        self.score = score
        self.status = status

    def color(self):
        return 'green' if self.status == Status.REVIEW \
            else 'green' if self.status == Status.OK \
            else 'bright_yellow' if self.status == Status.TESTING \
            else 'yellow' if self.status == Status.REJECTED \
            else 'red' if self.status == Status.PARTIAL \
            else 'white'
        # in standings CHECK has the same style as TESTING

    def bold(self):
        # TESTING is bold for more contrast with REJECTED
        return self.status in [Status.OK, Status.TESTING]

    def table_score(self):
        if self.status in [Status.TESTING, Status.REJECTED] and self.score is None:
            return '??'
        return self.score


class TaskInfo:
    def __init__(self, name, contest):
        self.name = name
        self.contest = contest


class StandingsRow:
    def __init__(self, place, user, tasks, solved, score, is_self, contest_id=None):
        self.place = place
        self.user = user
        self.tasks = tasks
        self.solved = solved
        self.score = score
        self.is_self = is_self
        self.contest_id = contest_id

    def color(self):
        return 'white'

    def bold(self):
        return self.is_self


class Standings:
    def __init__(self, tasks, rows, user=None):
        self.tasks = tasks
        self.rows = rows
        self.user = user

        self.contests = [
            contest
            for contest, tasks in groupby(self.tasks, lambda task: task.contest)
        ]

        self.tasks_by_contest = {
            contest: list(tasks)
            for contest, tasks in groupby(self.tasks, lambda task: task.contest)
        }

    def fix_is_self(self, user, contest_id):
        for row in self.rows:
            row.is_self = row.user == user and row.contest_id == contest_id


class Deadlines:
    FORMAT = '%Y/%m/%d %H:%M:%S MSK'
    PLACEHOLDER = '----/--/-- --:--:-- MSK (!)'

    def __init__(self, soft, hard):
        self.soft = soft
        self.hard = hard

    @staticmethod
    def is_close(deadline):
        from kks.util.storage import Config
        if deadline is None:
            return False
        dt = deadline - datetime.now(tz=timezone.utc)
        return dt < timedelta(days=Config().options.deadline_warning_days)

    @staticmethod
    def to_str(deadline):
        if deadline is None:
            return 'No deadline'
        result = deadline.strftime(Deadlines.FORMAT)
        if Deadlines.is_close(deadline):
            result += ' (!)'
        return result

    @staticmethod
    def parse(text, server_tz):
        """Parse datetime string (obtained from a problem page) and convert it to UTC"""
        dt = datetime.strptime(text, TIME_FORMAT)
        return dt.replace(tzinfo=server_tz).astimezone(MSK_TZ)


class ProblemInfo:
    """Subset of task info table used for max score estimation"""
    def __init__(  # TODO use dataclass?
        self,
        full_score: int,
        run_penalty: int, current_penalty: int,
        deadlines: Deadlines
    ):
        self.full_score = full_score
        self.run_penalty = run_penalty
        self.current_penalty = current_penalty
        self.deadlines = deadlines

    def active_deadline(self):
        if self.current_penalty >= self.full_score:
            return self.deadlines.hard
        return self.deadlines.soft or self.deadlines.hard

    def deadline_is_close(self):
        if self.past_deadline():
            return False
        return self.deadlines.is_close(self.active_deadline())

    def past_deadline(self):
        return (
            self.deadlines.hard is not None
            and datetime.now(tz=timezone.utc) > self.deadlines.hard
        )


class ContestInfo:
    def __init__(self, name, first_problem):
        self.name = name
        self.first_problem = first_problem

    def deadline_color(self):
        if self.past_deadline():
            return 'red'
        if self.active_deadline() is None:
            return 'green'
        if self.deadline_is_close():
            return 'bright_yellow'
        return 'yellow'

    def __getattr__(self, name):
        return getattr(self.first_problem, name)


class FullProblem(SummaryProblem):
    keep_info = ['Time limit:', 'Real time limit:', 'Memory limit:']

    @classmethod
    def load(cls, problem, session):
        from bs4 import BeautifulSoup

        page = session.get(problem.href)
        soup = BeautifulSoup(page.content, 'html.parser')
        task_area = soup.find('div', {'id': 'probNavTaskArea'})

        if task_area is not None:
            statement_html = cls.parse_statement(task_area)
            suffix = cls.guess_suffix(task_area)
        else:
            # closed contest, use API as fallback method
            api = session.api()
            prob_id = problem.extract_id()
            statement_html = BeautifulSoup(api.problem_statement(prob_id), 'html.parser')
            if 'Statement is not available' in statement_html.text:
                statement_html = None
            compilers = api.problem_status(prob_id).get('problem', {}).get('compilers', [])
            suffix = cls._lang_suf(compilers[0]) if compilers else None

        input_data, output_data = None, None
        if statement_html is not None:
            input_data, output_data = cls.parse_sample(statement_html)

        return cls(problem, page.url, input_data, output_data, statement_html, suffix)

    def __init__(self, problem, url, input_data, output_data, statement_html, suffix):
        super().__init__(**problem.__dict__)
        self.url = url
        self.input_data = input_data
        self.output_data = output_data
        self._html = statement_html
        self._suffix = suffix

    def suffix(self):
        if self._suffix is not None:
            return self._suffix
        pref = self.name.split('/', 1)[0]
        if pref == 'asm':
            return '.S'
        return '.c'

    @staticmethod
    def parse_sample(html):
        input_data, output_data = None, None

        input_title = html.find('h4', text='Input')
        if input_title is not None:
            input_data = input_title.find_next('pre').text
            # Add trailing newline, like in vim
            if not input_data.endswith('\n'):
                input_data += '\n'

        output_title = html.find('h4', text='Output')
        if output_title is not None:
            output_data = output_title.find_next('pre').text
            if not output_data.endswith('\n'):
                output_data += '\n'

        return input_data, output_data

    @staticmethod
    def parse_statement(html):
        from bs4 import BeautifulSoup
        from bs4.element import NavigableString

        soup = BeautifulSoup()
        problem_info = html.find('table', {'class': 'line-table-wb'})
        if problem_info is None:
            return None
        next_block = problem_info.find_next('h3', text='Submit a solution')
        if next_block is None:
            next_block = problem_info.find_next('h2')

        statement = soup.new_tag('body')

        info = soup.new_tag('table', border=1)
        info_avail = False
        for row in problem_info.find_all('tr'):
            key, value = row.find_all('td')
            if key.text in FullProblem.keep_info:
                info_avail = True
                info.append(copy(row))
                info.append('\n')

        if info_avail:
            statement.append('\n')
            statement.append(info)
            statement.append('\n')

        statement_avail = False
        curr = problem_info.next_sibling
        while curr is not next_block:  # next_block can be None, it's OK
            if not statement_avail and isinstance(curr, NavigableString) and curr.isspace():
                curr = curr.next_sibling
                continue  # skip leading spacing
            statement_avail = True
            statement.append(copy(curr))
            curr = curr.next_sibling

        if not statement_avail:
            return None

        html = soup.new_tag('html')
        head = soup.new_tag('head')
        head.append(soup.new_tag('meta', charset='utf-8'))
        html.append(head)
        html.append('\n')
        html.append(statement)
        return html

    @staticmethod
    def _lang_suf(lang_id):
        # NOTE compiler ids may change
        lang_id = int(lang_id)
        if lang_id in [2, 28, 51, 57, 61]:
            return '.c'
        if lang_id in [3, 29, 52, 58, 62]:
            return '.cpp'
        if lang_id in [25, 54]:
            return '.tar'
        if lang_id in [66, 67, 101, 102]:
            return '.S'
        return None

    @staticmethod
    def guess_suffix(html):
        form = html.find('form')
        if form is None:
            return None
        lang_list = form.find('select', {'name': 'lang_id'})
        if lang_list is None:
            lang_input = form.find('input', {'name': 'lang_id'})
            if lang_input is not None:
                return FullProblem._lang_suf(lang_input['value'])
            return None
        else:
            langs = [opt['value'] for opt in lang_list.find_all('option') if opt.get('value')]
            return FullProblem._lang_suf(langs[0])

    def statement_available(self):
        return self._html is not None

    def html(self):
        if not self.statement_available():
            return 'Statement is not available'
        return str(self._html)

    def markdown(self, width=100):
        if not self.statement_available():
            return 'Statement is not available'
        converter = HTML2Text(bodywidth=width, baseurl=self.url)
        converter.pad_tables = True
        return converter.handle(str(self._html))

    def attachments(self):
        """Returns a dict of attachments in form of {filename: url}"""
        if not self.statement_available():
            return {}
        attachments = {}
        for tag in self._html.find_all(['a', 'img']):
            url = tag['href'] if tag.name == 'a' else tag['src']
            parts = urlsplit(url)
            if parts.netloc != Links.HOST:
                continue
            query = parse_qs(parts.query)
            if 'file' in query:
                attachments[query['file'][0]] = url
        return attachments


def get_contest_id(group_id: str) -> int:
    return CONTEST_ID_BY_GROUP.get(group_id, None)


def get_group_id(contest_id: int) -> str:
    return GROUP_ID_BY_CONTEST.get(contest_id, None)


def get_contest_url(auth_data):
    return f'{Links.WEB_CLIENT_ROOT}?contest_id={auth_data.contest_id}'


def get_contest_url_with_creds(auth_data):
    url = get_contest_url(auth_data)
    if auth_data.login is not None and auth_data.password is not None:
        url += f'&login={urlquote(auth_data.login)}&password={urlquote(auth_data.password)}'
    return url


# NOTE all "ejudge_xxx" methods may raise kks.errors.AuthError
# If session was used previously to make a request, and no errors were raised, AuthError will not be raised
def ejudge_summary(session):
    from bs4 import BeautifulSoup

    page = session.get_page(Page.SUMMARY)

    soup = BeautifulSoup(page.content, 'html.parser')

    tasks = soup.find_all('td', class_='b1')

    problems = []
    for problem in chunks(tasks, 6):
        short, name, status, tests_passed, score, _ = problem

        problems.append(Problem(
            short.text,
            name.text,
            name.a['href'],
            status.text if not status.text.isspace() else Status.NOT_SUBMITTED,
            tests_passed.text if not tests_passed.text.isspace() else None,
            score.text if not score.text.isspace() else None
        ))

    return problems


def ejudge_standings(session):
    from bs4 import BeautifulSoup

    page = session.get_page(Page.USER_STANDINGS)
    soup = BeautifulSoup(page.content, 'html.parser')

    title = soup.find(class_='main_phrase').text
    name = title[:title.find('[') - 1]

    table = soup.find('table', class_='standings')
    rows = table.find_all('tr')

    tasks = [
        TaskInfo(task.text, extract_contest_name(task.text))
        for task in rows[0].find_all(class_='st_prob')
    ]

    # skip table header and stats at the bottom
    rows = rows[1:-3]

    def parse_rows():
        for row in rows:
            cells = row.find_all('td')  # search in html only once
            score_cells = [c for c in cells if 'st_prob' in c['class']]
            user = None
            place = None
            total = None
            score = None
            for c in cells:
                if 'st_team' in c['class']:
                    user = c.text
                if 'st_place' in c['class']:
                    place = c.text
                elif 'st_total' in c['class']:
                    total = c.text
                elif 'st_score' in c['class']:
                    score = c.text

            yield StandingsRow(
                place,
                user,
                [
                    to_task_score(task.contest, cell)
                    for task, cell in zip(tasks, score_cells)
                ],
                int(total),
                int(score),
                name == user
            )

    return Standings(tasks, list(parse_rows()), name)


def extract_contest_name(task_name):
    return task_name.split('-')[0]


def to_task_score(contest, cell):
    score = cell.text
    if not score or score.isspace():
        score = None

    status = Status.REVIEW if 'cell_attr_pr' in cell['class'] \
        else Status.REJECTED if 'cell_attr_rj' in cell['class'] \
        else Status.TESTING if 'cell_attr_tr' in cell['class'] \
        else Status.PARTIAL if score == '0' \
        else Status.OK if score is not None \
        else Status.NOT_SUBMITTED

    return TaskScore(contest, score, status)


def ejudge_submissions(session):
    from bs4 import BeautifulSoup

    page = session.get_page(Page.SUBMISSIONS, params={'all_runs': 1})

    soup = BeautifulSoup(page.content, 'html.parser')

    sub_table = soup.find('table', {'class': 'table'})
    if sub_table is None:
        return []
    submissions = [Submission.parse(row) for row in sub_table.find_all('tr')[1:]]
    submissions.sort(key=lambda x: x.problem)
    return {
        problem: list(subs) for problem, subs in groupby(submissions, lambda x: x.problem)
    }


def ejudge_report(link, session):
    from bs4 import BeautifulSoup

    page = session.get(link)
    soup = BeautifulSoup(page.content, 'html.parser')
    message_table = soup.find('table', {'class': 'message-table'})
    if message_table is not None:
        comments = message_table.find_all('tr')[1:]
    else:
        comments = []
    tests = soup.find('table', {'class': 'table'}).find_all('tr')[1:]
    return Report(comments, tests)


def ejudge_timezone(session):
    from bs4 import BeautifulSoup

    page = session.get_page(Page.MAIN_PAGE)
    soup = BeautifulSoup(page.content, 'html.parser')
    table = soup.find('table', {'class': 'info-table-line'})
    if table is None:
        raise ParseError('Cannot parse server time')
    offset_hours = None
    for row in table.find_all('tr'):
        cells = row.find_all('td')
        if len(cells) < 2:
            continue
        key, value, *_ = cells
        if 'Server time' in key.text:
            server_time = datetime.strptime(value.text, TIME_FORMAT)
            utc_time = datetime.utcnow()
            offset_hours = round((server_time - utc_time).total_seconds() / 3600)
            break
    if offset_hours is None:
        raise ParseError('Cannot parse server time')
    return timezone(timedelta(hours=offset_hours))


def get_contest_deadlines(session, summary, no_cache):
    from kks.util.storage import Cache

    names = [problem.short_name for problem in summary]

    contest_names = []
    first_problems = []
    for contest, problems in groupby(summary, lambda problem: problem.contest()):
        contest_names.append(contest)
        first_problems.append(next(problems).short_name)

    with Cache('problem_info', compress=True, version=PROBLEM_INFO_VERSION).load() as cache:
        if no_cache:
            for problem in summary:
                cache.erase(CacheKeys.deadline(problem.contest()))
            cache.erase(CacheKeys.server_tz)

        problems = update_cached_problems(
            cache, names, session, problems=first_problems, summary=summary
        )

    return [ContestInfo(name, problem) for name, problem in zip(contest_names, problems)]


def update_cached_problems(cache, names, session, problems=None, summary=None):
    # names - latest list of problem names
    # problems - names of problems to be updated

    def cached_problem(problem):
        return BaseProblem(problem.short_name, problem.href)

    problem_list = cache.get(CacheKeys.problem_links, [])  # we can avoid loading summary
    if len(problem_list) != len(names) or \
            any(problem.short_name != name for problem, name in zip(problem_list, names)):
        problem_list = summary or ejudge_summary(session)
        problem_list = [cached_problem(p) for p in problem_list]
        cache.set(CacheKeys.problem_links, problem_list)

    if problems is not None:
        problem_list = [problem for problem in problem_list if problem.short_name in problems]

    with tqdm(total=len(problem_list), leave=False) as pbar:
        def with_progress(func, *args, **kwargs):
            result = func(*args, **kwargs)
            pbar.update(1)
            return result

        return [
            with_progress(get_problem_info, problem, cache, session) for problem in problem_list
        ]


def get_problem_info(problem, cache, session):
    from bs4 import BeautifulSoup

    # NOTE penalties are assumed to be the same for all tasks in a contest, it may be wrong

    full_scores = cache.get(CacheKeys.full_scores, {})
    run_penalties = cache.get(CacheKeys.run_penalties, {})

    full_score = full_scores.get(problem.short_name)
    run_penalty = run_penalties.get(problem.short_name)

    penalty_key = CacheKeys.penalty(problem.contest())
    current_penalty = cache.get(penalty_key)

    deadline_key = CacheKeys.deadline(problem.contest())
    deadlines = cache.get(deadline_key)

    # new problem or need to update penalty
    need_loading = any(
        field is None for field in [full_score, run_penalty, current_penalty, deadlines]
    )

    if not need_loading:
        return ProblemInfo(full_score, run_penalty, current_penalty, deadlines)

    def update_cache(full_score, run_penalty, current_penalty, deadlines):
        result = ProblemInfo(full_score, run_penalty, current_penalty, deadlines)
        full_scores[problem.short_name] = full_score
        run_penalties[problem.short_name] = run_penalty
        cache.set(CacheKeys.full_scores, full_scores)
        cache.set(CacheKeys.run_penalties, run_penalties)

        # kr tasks don't have soft deadlines, so their data should not expire
        if result.past_deadline() or problem.contest().startswith('kr'):
            expiration = None
        else:
            if deadlines.soft is not None:
                expiration = deadlines.soft
            else:
                expiration = timedelta(days=4, hours=23, minutes=55)

        cache.set(penalty_key, current_penalty, expiration)
        # deadlines may be shifted or there may (?) be multiple soft deadlines, so they should expire too
        cache.set(deadline_key, deadlines, expiration)

        return result

    page = session.get(problem.href)
    soup = BeautifulSoup(page.content, 'html.parser')
    task_area = soup.find('div', {'id': 'probNavTaskArea'})  # will be None for a closed contest
    problem_info = None
    if task_area is not None:
        # if problem_info is None, we assume the problem is past the deadline
        problem_info = task_area.find('table', {'class': 'line-table-wb'})

    full_score = 0
    run_penalty = 0  # may be incorrect for kr
    current_penalty = 0
    deadlines = Deadlines(None, None)
    full_score_found = False

    if problem_info is None:
        deadlines.hard = datetime.fromtimestamp(0, tz=timezone.utc)
    else:
        for row in problem_info.find_all('tr'):
            key, value = row.find_all('td')
            if key.text == 'Full score:':
                full_score = int(value.text)
                full_score_found = True
            elif key.text == 'Run penalty:':
                run_penalty = int(value.text)
            elif key.text == 'Current penalty:':
                current_penalty = int(value.text)
            elif key.text == 'Next soft deadline:':
                deadlines.soft = Deadlines.parse(value.text, get_server_tz(cache, session))
            elif key.text == 'Deadline:':
                deadlines.hard = Deadlines.parse(value.text, get_server_tz(cache, session))

    if not full_score_found:
        try:
            problem_status = session.api().problem_status(problem.extract_id()).get('problem', {})
        except APIError as e:
            click.secho(f'Cannot get problem info ({problem.short_name}): {e}', err=True)
            problem_status = {}
        # NOTE for running / testing kr contests full_score == 1
        full_score = problem_status.get('full_score', 0)
        run_penalty = problem_status.get('run_penalty', 0)
        # API never tells the deadlines and current penalty

    return update_cache(full_score, run_penalty, current_penalty, deadlines)


def get_server_tz(cache, session):
    tz = cache.get(CacheKeys.server_tz, None)
    if tz is None:
        tz = ejudge_timezone(session)
        cache.set(CacheKeys.server_tz, tz, expiration=timedelta(days=7))
    return tz


def chunks(iterable, chunk_size):
    for i in range(0, len(iterable), chunk_size):
        yield iterable[i:i + chunk_size]
