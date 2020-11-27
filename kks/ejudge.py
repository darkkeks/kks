from itertools import groupby
from urllib.parse import urlparse, parse_qs, quote as urlquote

import click
import requests
from bs4 import BeautifulSoup


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
    REJECTED = 'Rejected'
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
            else 'red'

    def bold(self):
        return self.status == Status.OK


class TaskScore:
    def __init__(self, contest, task_name, score, status):
        self.contest = contest
        self.task_name = task_name
        self.score = score
        self.status = status

    def color(self):
        return 'green' if self.status == Status.REVIEW \
            else 'green' if self.status == Status.OK \
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
        else Status.OK if score is not None \
        else Status.NOT_SUBMITTED

    return TaskScore(extract_contest_name(task_name), task_name, score, status)


def ejudge_sample(problem_link, session):
    page = session.get(problem_link)
    soup = BeautifulSoup(page.content, 'html.parser')

    input_data, output_data = None, None

    input_title = soup.find('h4', text='Input')
    if input_title is not None:
        input_data = input_title.find_next('pre').text

    output_title = soup.find('h4', text='Output')
    if output_title is not None:
        output_data = output_title.find_next('pre').text

    return input_data, output_data


def compose_post_data(form, lang_callback):
    lang_list = form.find('select', {'name': 'lang_id'})
    if lang_list is None:
        lang_input = form.find('input', {'name': 'lang_id'})
        if lang_input is not None:
            lang = lang_input['value']
    else:
        langs = [(opt.text, opt['value']) for opt in lang_list.find_all('option') if opt.get('value')]
        if len(langs) == 1:
            lang = langs[0][1]
        else:
            lang = lang_callback(langs)[1]

    data = {
        'lang_id': lang,
    }
    for elem in form.find_all('input'):
        if elem.get('name') not in ['lang_id', 'file'] and elem.get('value') is not None:
            data[elem['name']] = elem['value']
    return data


def submit_ok(req):
    return 'view-problem-submit' in req.url


def get_error_msg(req):
    if 'This submit is duplicate of another run' in req.text:
        return 'Duplicate of another run'


def may_resubmit(runs):
    """ask for a confirmation if an accepted solution exists"""
    rows = runs.find_all('tr')
    if len(rows) < 2:
        return True
    last_run = rows[1]
    if last_run.find_all('td')[5].text not in [Status.OK, Status.REVIEW]:
        return True
    return click.confirm('This problem was already solved! Submit anyway?')


def ejudge_submit(links, session, file, prob_id, lang_callback):
    problems = ejudge_summary(links, session)
    if problems is None:
        return False, 'Auth error'
    matching = [p for p in problems if p.short_name == prob_id]
    if not matching:
        return False, 'Invalid problem ID'
    problem_link = matching[0].href
    page = session.get(problem_link)
    soup = BeautifulSoup(page.content, 'html.parser')

    runs = soup.find('table', {'class': 'table'})
    if runs is not None:
        if not may_resubmit(runs):
            return False, 'Cancelled by user'

    form = soup.find('form')
    if form is None:
        return False, 'Cannot submit a solution for this problem'
    submit_url = form['action']
    headers = {'Referer': problem_link}
    data = compose_post_data(form, lang_callback)
    files = {
        'file': (file, open(file, 'rb')),
    }

    req = session.post(submit_url, headers=headers, data=data, files=files)
    if submit_ok(req):
        return True, 'Success!'
    else:
        return False, get_error_msg(req)


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
