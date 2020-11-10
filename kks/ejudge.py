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

    tasks = soup.find_all('td', {'class': 'b1'})

    problems = []
    for problem in chunks(tasks, 6):
        short, name, status, tests_passed, score, _ = problem

        problems.append(Problem(
            short.text,
            name.text,
            name.a['href'],
            status.text if not status.text.isspace() else Status.NOT_SUBMITTED,
            tests_passed.text if not tests_passed.text.isspace() else None,
            score.text if not score.text.isspace() else 0
        ))

    return problems


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
