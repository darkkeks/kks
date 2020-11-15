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
    def __init__(self, score, status):
        self.score = score
        self.status = status

    def color(self):
        return 'green' if self.status == Status.REVIEW \
            else 'green' if self.status == Status.OK \
            else 'white'

    def bold(self):
        return self.status == Status.OK


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


def ejudge_auth(auth_data, session):
    url = f'https://caos.ejudge.ru/ej/client?contest_id={auth_data.contest_id}'

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
        return None

    page = session.get(standings)
    soup = BeautifulSoup(page.content, 'html.parser')

    title = soup.find(class_='main_phrase').text
    name = title[:title.find('[') - 1]

    table = soup.find('table', class_='standings')
    rows = table.find_all('tr')

    # skip table header and stats at the bottom
    rows = rows[1:-3]

    for row in rows:
        user = row.find(class_='st_team').text
        tasks = row.find_all(class_='st_prob')

        yield StandingsRow(
            row.find(class_='st_place').text,
            user,
            [to_task_score(task) for task in tasks],
            int(row.find(class_='st_total').text),
            int(row.find(class_='st_score').text),
            name == user
        )


def to_task_score(task):
    score = task.text
    if score.isspace():
        score = None

    status = Status.REVIEW if 'cell_attr_pr' in task['class'] \
        else Status.OK if score is not None \
        else Status.NOT_SUBMITTED

    return TaskScore(score, status)


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
