from copy import copy
from datetime import datetime, timedelta
from itertools import groupby
from urllib.parse import quote as urlquote

# import requests  # we use lazy imports to improve load time for local commands
# from bs4 import BeautifulSoup
# from bs4.element import NavigableString

from kks.util.h2t import HTML2Text

CONTEST_ID_BY_GROUP = {
    int('19' + str(i)): 130 + i
    for i in range(1, 12)
}


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


class Problem:
    def __init__(self, short_name, name, href, status, tests_passed, score):
        self.short_name = short_name
        self.name = name
        self.href = href  # NOTE contains SID -> quickly becomes outdated
        self.status = status
        self.tests_passed = tests_passed
        self.score = score

    def color(self):
        return 'green' if self.status == Status.OK \
            else 'green' if self.status == Status.REVIEW \
            else 'white' if self.status == Status.NOT_SUBMITTED \
            else 'bright_yellow' if self.status == Status.CHECK \
            else 'bright_yellow' if self.status == Status.TESTING \
            else 'red'

    def bold(self):
        return self.status == Status.OK


class Submission:
    def __init__(self, row):
        cells = row.find_all('td')
        self.id = int(cells[0].text)
        self.problem = cells[3].text
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
    def __init__(self, contest, score, status):
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
    def __init__(self, tasks, rows):
        self.tasks = tasks
        self.rows = rows

        self.contests = [
            contest
            for contest, tasks in groupby(self.tasks, lambda task: task.contest)
        ]

        self.tasks_by_contest = {
            contest: list(tasks)
            for contest, tasks in groupby(self.tasks, lambda task: task.contest)
        }


class ProblemInfo:
    """Subset of task info table used for max score estimation"""

    def __init__(self, full_score, run_penalty, current_penalty):
        self.full_score = full_score
        self.run_penalty = run_penalty
        self.current_penalty = current_penalty


class Statement:
    keep_info = ['Time limit:', 'Real time limit:', 'Memory limit:']

    def __init__(self, page):
        from bs4 import BeautifulSoup
        from bs4.element import NavigableString

        self.input_data = None
        self.output_data = None
        self._html = None
        self.url = page.url

        soup = BeautifulSoup(page.content, 'html.parser')
        task_area = soup.find('div', {'id': 'probNavTaskArea'})

        input_title = task_area.find('h4', text='Input')
        if input_title is not None:
            self.input_data = input_title.find_next('pre').text

        output_title = task_area.find('h4', text='Output')
        if output_title is not None:
            self.output_data = output_title.find_next('pre').text

        problem_info = task_area.find('table', {'class': 'line-table-wb'})
        if problem_info is None:
            return
        next_block = problem_info.find_next('h3', text='Submit a solution')
        if next_block is None:
            next_block = problem_info.find_next('h2')

        statement = soup.new_tag('body')

        info = soup.new_tag('table', border=1)
        info_avail = False
        for row in problem_info.find_all('tr'):
            key, value = row.find_all('td')
            if key.text in Statement.keep_info:
                info_avail = True
                info.append(copy(row))

        if info_avail:
            statement.append(info)

        statement_avail = False
        curr = problem_info.next_sibling
        while curr is not next_block:  # next_block can be None, it's OK
            if not statement_avail and isinstance(curr, NavigableString) and curr.isspace():
                curr = curr.next_sibling
                continue  # skip leading spacing
            statement_avail = True
            statement.append(copy(curr))
            curr = curr.next_sibling

        if statement_avail:
            html = soup.new_tag('html')
            head = soup.new_tag('head')
            head.append(soup.new_tag('meta', charset='utf-8'))
            html.append(head)
            html.append(statement)
            self._html = html

    def html(self):
        if self._html is None:
            return 'Statement is not available'
        # NOTE "kks convert statement.html" will produce a slightly different .md file (more spaces, but rendered markdown is not affected)
        return self._html.prettify()

    def markdown(self, width=100):
        if self._html is None:
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
            user = row.find(class_='st_team').text
            score_cells = row.find_all(class_='st_prob')

            yield StandingsRow(
                row.find(class_='st_place').text,
                user,
                [
                    to_task_score(task.contest, cell)
                    for task, cell in zip(tasks, score_cells)
                ],
                int(row.find(class_='st_total').text),
                int(row.find(class_='st_score').text),
                name == user
            )

    return Standings(tasks, list(parse_rows()))


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


def ejudge_statement(problem_link, session):
    page = session.get(problem_link)
    return Statement(page)


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


def get_problem_info(problem, cache, session):
    from bs4 import BeautifulSoup

    # NOTE penalties are assumed to be the same for all tasks in a contest, it may be wrong

    need_loading = False

    full_scores = cache.get('full', {})
    run_penalties = cache.get('run', {})

    full_score = full_scores.get(problem.short_name)
    run_penalty = run_penalties.get(problem.short_name)

    penalty_key = f'p_{problem.contest}'
    current_penalty = cache.get(penalty_key)

    if full_score is None or run_penalty is None or current_penalty is None:  # new problem or need to update penalty
        need_loading = True

    if not need_loading:
        return ProblemInfo(full_score, run_penalty, current_penalty)

    now = datetime.now()
    def update_cache(full_score, run_penalty, current_penalty, soft_dl, hard_dl):
        past_deadline = hard_dl is not None and now > hard_dl

        if past_deadline:
            # see issue #72
            full_score = 0
            current_penalty = 0

        full_scores[problem.short_name] = full_score
        run_penalties[problem.short_name] = run_penalty
        cache.set('full', full_scores)
        cache.set('run', run_penalties)

        if current_penalty >= full_score and current_penalty != 0 or past_deadline:
            expiration = None
            # max_score = 0, will not change
            # NOTE may need patching for kr contests
        else:
            if soft_dl is not None:
                expiration = soft_dl
            else:
                expiration = timedelta(days=4, hours=23, minutes=55)

        cache.set(penalty_key, current_penalty, expiration)

        return ProblemInfo(full_score, run_penalty, current_penalty)

    page = session.get(problem.href)
    soup = BeautifulSoup(page.content, 'html.parser')
    task_area = soup.find('div', {'id': 'probNavTaskArea'})
    problem_info = task_area.find('table', {'class': 'line-table-wb'})

    full_score = 0
    run_penalty = 0  # may be incorrect for kr
    current_penalty = 0
    soft_dl = None
    hard_dl = None

    if problem_info is None:
        # may happen in kr contests?
        return update_cache(full_score, run_penalty, current_penalty, None)

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
            soft_dl = datetime.strptime(value.text, '%Y/%m/%d %H:%M:%S')
        elif key.text == 'Deadline:':
            hard_dl = datetime.strptime(value.text, '%Y/%m/%d %H:%M:%S')

    return update_cache(full_score, run_penalty, current_penalty, soft_dl, hard_dl)


def chunks(iterable, chunk_size):
    for i in range(0, len(iterable), chunk_size):
        yield iterable[i:i + chunk_size]
