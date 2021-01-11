from copy import copy
from itertools import groupby
from urllib.parse import quote as urlquote

import click
import requests
from bs4 import BeautifulSoup
from bs4.element import NavigableString

from kks.util.h2t import HTML2Text

CONTEST_ID_BY_GROUP = {
    int('19' + str(i)): 130 + i
    for i in range(1, 12)
}


class LinkTypes:
    SETTINGS = 'Settings'
    SUMMARY = 'Summary'
    SUBMISSIONS = 'Submissions'
    USER_STANDINGS = 'User standings'
    SUBMIT_CLAR = 'Submit clar'
    CLARS = 'Clars'


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
        self.href = href
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

        has_failed_tests = False

        for test in tests:
            t_id, status, *_ = map(lambda cell: cell.text, test.find_all('td'))
            if status != Status.OK:
                if not has_failed_tests:
                    if comments:
                        self.lines.append('\n')
                    self.lines.append(f'Total tests: {len(tests)}\n')
                    self.lines.append('Failed tests:\n')
                    has_failed_tests = True
                self.lines.append(f'{t_id} - {status}\n')

    def as_comment(self):
        sep_lines = 3
        return ''.join('// ' + line for line in self.lines) + '\n' * sep_lines


class TaskScore:
    def __init__(self, contest, task_name, score, status):
        self.contest = contest
        self.task_name = task_name
        self.score = score
        self.status = status

    def color(self):
        return 'green' if self.status == Status.REVIEW \
            else 'green' if self.status == Status.OK \
            else 'bright_yellow' if self.status == Status.TESTING \
            else 'red' if self.status == Status.PARTIAL \
            else 'white'

    def bold(self):
        return self.status == Status.OK


class Standings:
    def __init__(self, task_names, rows):
        self.task_names = task_names
        self.rows = rows

        self.contests = [contest for contest, _ in groupby(task_names, extract_contest_name)]

        self.tasks_by_contest = {
            contest: list(tasks)
            for contest, tasks in groupby(task_names, extract_contest_name)
        }


class StandingsRow:
    def __init__(self, place, user, tasks, solved, score, is_self):
        self.place = place
        self.user = user
        self.tasks = tasks
        self.solved = solved
        self.score = score
        self.is_self = is_self

    def color(self):
        return 'white'

    def bold(self):
        return self.is_self


class Statement:

    keep_info = ['Time limit:', 'Real time limit:', 'Memory limit:']

    def __init__(self, page):
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
        return self._html.prettify()

    def markdown(self, width=100):
        if self._html is None:
            return 'Statement is not available'
        converter = HTML2Text(bodywidth=width, baseurl=self.url)
        converter.pad_tables = True
        return converter.handle(str(self._html))


def get_contest_id(group_id):
    return CONTEST_ID_BY_GROUP.get(group_id, None)


def get_contest_url(auth_data):
    return f'https://caos.ejudge.ru/ej/client?contest_id={auth_data.contest_id}'


def get_contest_url_with_creds(auth_data):
    url = get_contest_url(auth_data)
    if auth_data.login is not None and auth_data.password is not None:
        url += f'&login={urlquote(auth_data.login)}&password={urlquote(auth_data.password)}'
    return url


def ejudge_auth(auth_data, session):
    url = get_contest_url(auth_data)

    page = session.post(url, data={
        'login': auth_data.login,
        'password': auth_data.password
    })

    if page.status_code != requests.codes.ok:
        click.secho(f'Failed to authenticate (status code {page.status_code})', err=True, fg='red')

    soup = BeautifulSoup(page.content, 'html.parser')

    if 'Invalid contest' in soup.text or 'invalid contest_id' in soup.text:
        click.secho(f'Invalid contest (contest id {auth_data.contest_id})', fg='red', err=True)
        return None

    if 'Permission denied' in soup.text:
        click.secho('Permission denied (invalid username, password or contest id)', fg='red', err=True)
        return None

    buttons = soup.find_all('a', {'class': 'menu'}, href=True)

    return {
        button.text: button['href']
        for button in buttons
    }


def ejudge_summary(links, session):
    summary = links.get(LinkTypes.SUMMARY, None)
    if summary is None:
        return None

    page = session.get(summary)
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


def ejudge_standings(links, session):
    standings = links.get(LinkTypes.USER_STANDINGS, None)
    if standings is None:
        return None, None

    page = session.get(standings)
    soup = BeautifulSoup(page.content, 'html.parser')

    title = soup.find(class_='main_phrase').text
    name = title[:title.find('[') - 1]

    table = soup.find('table', class_='standings')
    rows = table.find_all('tr')

    task_names = [task.text for task in rows[0].find_all(class_='st_prob')]

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
                    to_task_score(task_name, cell)
                    for task_name, cell in zip(task_names, score_cells)
                ],
                int(row.find(class_='st_total').text),
                int(row.find(class_='st_score').text),
                name == user
            )

    return Standings(task_names, parse_rows())


def extract_contest_name(task_name):
    return task_name.split('-')[0]


def to_task_score(task_name, cell):
    score = cell.text
    if score.isspace():
        score = None

    status = Status.REVIEW if 'cell_attr_pr' in cell['class'] \
        else Status.REJECTED if 'cell_attr_rj' in cell['class'] \
        else Status.TESTING if 'cell_attr_tr' in cell['class'] \
        else Status.PARTIAL if score == '0' \
        else Status.OK if score is not None \
        else Status.NOT_SUBMITTED

    if status == Status.TESTING and score is None:
        score = '??'

    return TaskScore(extract_contest_name(task_name), task_name, score, status)


def ejudge_statement(problem_link, session):
    page = session.get(problem_link)
    return Statement(page)


def ejudge_submissions(links, session):
    link = links.get(LinkTypes.SUBMISSIONS, None)
    if link is None:
        return []

    page = session.get(link, params={'all_runs': 1})
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
    page = session.get(link)
    soup = BeautifulSoup(page.content, 'html.parser')
    message_table = soup.find('table', {'class': 'message-table'})
    if message_table is not None:
        comments = message_table.find_all('tr')[1:]
    else:
        comments = []
    tests = soup.find('table', {'class': 'table'}).find_all('tr')[1:]
    return Report(comments, tests)


def check_session(links, session):
    summary = links.get(LinkTypes.SUMMARY, None)
    if summary is None:
        return False
    response = session.get(summary)
    if 'Invalid session' in response.text:
        return False
    return True


def chunks(iterable, chunk_size):
    for i in range(0, len(iterable), chunk_size):
        yield iterable[i:i + chunk_size]
