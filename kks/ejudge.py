from copy import copy
from datetime import datetime, timedelta
from itertools import groupby
from typing import Optional
from urllib.parse import quote as urlquote

# import requests  # we use lazy imports to improve load time for local commands
# from bs4 import BeautifulSoup
# from bs4.element import NavigableString
from tqdm import tqdm

from kks.util.h2t import HTML2Text


CONTEST_ID_BY_GROUP = {
    int('19' + str(i)): 130 + i
    for i in range(1, 12)
}


PROBLEM_INFO_VERSION = 2


class Links:
    WEB_CLIENT_ROOT = 'https://caos.ejudge.ru/ej/client'
    SETTINGS = f'{WEB_CLIENT_ROOT}/view-settings/S__SID__'
    SUMMARY = f'{WEB_CLIENT_ROOT}/view-problem-summary/S__SID__'
    SUBMISSIONS = f'{WEB_CLIENT_ROOT}/view-submissions/S__SID__'
    USER_STANDINGS = f'{WEB_CLIENT_ROOT}/standings/S__SID__'
    SUBMIT_CLAR = f'{WEB_CLIENT_ROOT}/view-clar-submit/S__SID__'
    CLARS = f'{WEB_CLIENT_ROOT}/view-clars/S__SID__'


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
        # TODO use API? (see #68)
        page = session.get(self.href)
        return FullProblem(self, page)


class ProblemWithDeadline:
    def __init__(self, problem, contest):
        self._problem = problem
        self._contest = contest

    def deadline_is_close(self):
        return self._contest.deadlines.is_close()

    def deadline_color(self):
        return self._contest.deadline_color()

    def deadline_string(self):
        return self._contest.deadlines.format_soft()

    def __getattr__(self, name):
        return getattr(self._problem, name)


class CacheKeys:
    @staticmethod
    def penalty(contest):
        return f'p_{contest}'

    @staticmethod
    def deadline(contest):
        return f'dl_{contest}'


class Submission:
    def __init__(self, row):
        cells = row.find_all('td')
        self.id = int(cells[0].text)
        self.problem = cells[3].text
        self.compiler = cells[4].text
        self.status = cells[5].text
        self.source = cells[8].find('a')['href'].replace('view-source', 'download-run')
        report_link = cells[9].find('a')
        self.report = report_link['href'] if report_link is not None else None

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
                yield from f'Comment by {author}: {comment.text.strip()}\n'.splitlines(keepends=True)

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

    def is_close(self):
        from kks.util.storage import Config
        if self.soft is None:
            return False
        dt = self.soft - datetime.now()
        return dt < timedelta(days=Config().options.deadline_warning_days)

    def format_soft(self):
        deadline = self.soft
        if deadline is None:
            return 'No deadline'
        result = deadline.strftime(Deadlines.FORMAT)
        if self.is_close():
            result += ' (!)'
        return result



class ProblemInfo:
    """Subset of task info table used for max score estimation"""
    def __init__(self, full_score: int, run_penalty: int, current_penalty: int, deadlines: Deadlines):
        self.full_score = full_score
        self.run_penalty = run_penalty
        self.current_penalty = current_penalty
        self.deadlines = deadlines

    def past_deadline(self):
        return self.deadlines.hard is not None and datetime.now() > self.deadlines.hard or self.current_penalty >= self.full_score


class ContestInfo:
    def __init__(self, name, first_problem):
        self.name = name
        self.first_problem = first_problem

    def deadline_color(self):
        if self.past_deadline():
            return 'red'
        if self.deadlines.soft is None:
            return 'green'
        if self.deadlines.is_close():
            return 'bright_yellow'
        return 'yellow'

    def __getattr__(self, name):
        return getattr(self.first_problem, name)

class FullProblem(SummaryProblem):
    keep_info = ['Time limit:', 'Real time limit:', 'Memory limit:']

    def __init__(self, problem, page):
        super().__init__(**problem.__dict__)
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(page.content, 'html.parser')
        task_area = soup.find('div', {'id': 'probNavTaskArea'})

        self.input_data, self.output_data = self.parse_sample(task_area)
        self._html = self.parse_statement(task_area)
        self._suffix = self.guess_suffix(task_area)
        self.url = page.url

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

        output_title = html.find('h4', text='Output')
        if output_title is not None:
            output_data = output_title.find_next('pre').text

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
    def guess_suffix(html):

        def get_suf(lang_id):
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

        form = html.find('form')
        if form is None:
            return None
        lang_list = form.find('select', {'name': 'lang_id'})
        if lang_list is None:
            lang_input = form.find('input', {'name': 'lang_id'})
            if lang_input is not None:
                return get_suf(lang_input['value'])
            return None
        else:
            langs = [opt['value'] for opt in lang_list.find_all('option') if opt.get('value')]
            return get_suf(langs[0])

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


def get_contest_id(group_id):
    return CONTEST_ID_BY_GROUP.get(group_id, None)


def get_group_id(contest_id):
    for group, contest in CONTEST_ID_BY_GROUP.items():
        if contest_id == contest:
            return group
    return None


def get_contest_url(auth_data):
    return f'https://caos.ejudge.ru/ej/client?contest_id={auth_data.contest_id}'


def get_contest_url_with_creds(auth_data):
    url = get_contest_url(auth_data)
    if auth_data.login is not None and auth_data.password is not None:
        url += f'&login={urlquote(auth_data.login)}&password={urlquote(auth_data.password)}'
    return url


# NOTE all "ejudge_xxx" methods may raise kks.errors.AuthError
# If session was used previously to make a request, and no errors were raised, AuthError will not be raised
def ejudge_summary(session):
    from bs4 import BeautifulSoup

    page = session.get(Links.SUMMARY)

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

    page = session.get(Links.USER_STANDINGS)
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

    page = session.get(Links.SUBMISSIONS, params={'all_runs': 1})

    soup = BeautifulSoup(page.content, 'html.parser')

    sub_table = soup.find('table', {'class': 'table'})
    if sub_table is None:
        return []
    submissions = [Submission(row) for row in sub_table.find_all('tr')[1:]]
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

        problems = update_cached_problems(cache, names, session, problems=first_problems, summary=summary)

    return [ContestInfo(name, problem) for name, problem in zip(contest_names, problems)]


def update_cached_problems(cache, names, session, problems=None, summary=None):
    # names - latest list of problem names
    # problems - names of problems to be updated

    def cached_problem(problem):
        return BaseProblem(problem.short_name, problem.href)

    problem_list = cache.get('problem_links', [])  # we can avoid loading summary
    if len(problem_list) != len(names) or \
            any(problem.short_name != name for problem, name in zip(problem_list, names)):
        problem_list = summary or ejudge_summary(session)
        problem_list = [cached_problem(p) for p in problem_list]
        cache.set('problem_links', problem_list)

    if problems is not None:
        problem_list = [problem for problem in problem_list if problem.short_name in problems]

    with tqdm(total=len(problem_list), leave=False) as pbar:
        def with_progress(func, *args, **kwargs):
            result = func(*args, **kwargs)
            pbar.update(1)
            return result

        return [with_progress(get_problem_info, problem, cache, session) for problem in problem_list]


def get_problem_info(problem, cache, session):
    from bs4 import BeautifulSoup

    # NOTE penalties are assumed to be the same for all tasks in a contest, it may be wrong

    need_loading = False

    full_scores = cache.get('full', {})
    run_penalties = cache.get('run', {})

    full_score = full_scores.get(problem.short_name)
    run_penalty = run_penalties.get(problem.short_name)

    penalty_key = CacheKeys.penalty(problem.contest())
    current_penalty = cache.get(penalty_key)

    deadline_key = CacheKeys.deadline(problem.contest())
    deadlines = cache.get(deadline_key)

    need_loading = any(field is None for field in [full_score, run_penalty, current_penalty, deadlines])  # new problem or need to update penalty

    if not need_loading:
        return ProblemInfo(full_score, run_penalty, current_penalty, deadlines)

    def update_cache(full_score, run_penalty, current_penalty, deadlines):
        result = ProblemInfo(full_score, run_penalty, current_penalty, deadlines)
        full_scores[problem.short_name] = full_score
        run_penalties[problem.short_name] = run_penalty
        cache.set('full', full_scores)
        cache.set('run', run_penalties)

        if result.past_deadline():
            expiration = None
            # max_score = 0, will not change
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
    task_area = soup.find('div', {'id': 'probNavTaskArea'})
    problem_info = task_area.find('table', {'class': 'line-table-wb'})

    full_score = 0
    run_penalty = 0  # may be incorrect for kr
    current_penalty = 0
    deadlines = Deadlines(None, None)

    if problem_info is None:
        # if this ever happens, we assume the problem is past the deadline
        deadlines.hard = datetime.fromtimestamp(0)
        return update_cache(full_score, run_penalty, current_penalty, deadlines)

    # TODO "Full score" can be missing (sm01-3)
    # in this case we should use max score from the table as full
    for row in problem_info.find_all('tr'):
        key, value = row.find_all('td')
        if key.text == 'Full score:':
            full_score = int(value.text)
        elif key.text == 'Run penalty:':
            run_penalty = int(value.text)
        elif key.text == 'Current penalty:':
            current_penalty = int(value.text)
        elif key.text == 'Next soft deadline:':
            deadlines.soft = datetime.strptime(value.text, '%Y/%m/%d %H:%M:%S')
        elif key.text == 'Deadline:':
            deadlines.hard = datetime.strptime(value.text, '%Y/%m/%d %H:%M:%S')

    return update_cache(full_score, run_penalty, current_penalty, deadlines)


def chunks(iterable, chunk_size):
    for i in range(0, len(iterable), chunk_size):
        yield iterable[i:i + chunk_size]
