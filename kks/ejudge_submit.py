import click
from bs4 import BeautifulSoup

from kks.ejudge import Status, ejudge_summary
from kks.util.common import prompt_choice


class ProblemPage:
    def __init__(self, link, runs, form):
        self.link = link
        self.runs = runs
        self.form = form


def submit_ok(req):
    return 'view-problem-submit' in req.url


def get_error_msg(req):
    if 'This submit is duplicate of another run' in req.text:
        return 'Duplicate of another run'
    if 'Error: Empty submit' in req.text:
        return 'Empty submit'
    print(req.status_code, req.url, req.text)
    return 'Unknown error'


def may_resubmit(runs):
    """ask for a confirmation if an accepted solution exists"""
    rows = runs.find_all('tr')
    if len(rows) < 2:
        return True
    last_run = rows[1]
    if last_run.find_all('td')[5].text not in [Status.OK, Status.REVIEW, Status.TESTING, Status.CHECK]:
        return True
    return click.confirm('This problem was already solved! Submit anyway?')


def _get_problem_data(links, session, prob_id):
    problems = ejudge_summary(links, session)
    if problems is None:
        return None, 'Auth error'
    matching = [p for p in problems if p.short_name == prob_id]
    if not matching:
        return None, 'Invalid problem ID'
    problem_link = matching[0].href
    page = session.get(problem_link)
    soup = BeautifulSoup(page.content, 'html.parser')

    runs = soup.find('table', {'class': 'table'})
    form = soup.find('form')

    if form is None:
        return None, 'Cannot submit a solution for this problem'
    file = form.find('input', {'name': 'file'})
    if file is None:
        return None, 'Cannot submit a solution for this problem'

    return ProblemPage(problem_link, runs, form), ''


def compose_post_data(form):
    def lang_choice(langs):
        choices = [e[0] for e in langs]
        lang_id = prompt_choice('Select a language / compiler', choices)
        return langs[lang_id]

    lang_list = form.find('select', {'name': 'lang_id'})
    if lang_list is None:
        lang_input = form.find('input', {'name': 'lang_id'})
        if lang_input is not None:
            lang = lang_input['value']
        else:
            lang = None
    else:
        langs = [(opt.text, opt['value']) for opt in lang_list.find_all('option') if opt.get('value')]
        if len(langs) == 1:
            lang = langs[0][1]
        else:
            lang = lang_choice(langs)[1]

    data = {}
    if lang is not None:
        data['lang_id'] = lang
    for elem in form.find_all('input'):
        if elem.get('name') not in ['lang_id', 'file'] and elem.get('value') is not None:
            data[elem['name']] = elem['value']
    return data


def submit_request(session, page, file):
    headers = {'Referer': page.link}
    url = page.form['action']
    data = compose_post_data(page.form)
    files = {
        'file': (file.name, open(file, 'rb')),
    }
    return session.post(url, headers=headers, data=data, files=files)


def submit_solution(links, session, file, prob_id):
    page, msg = _get_problem_data(links, session, prob_id)
    if page is None:
        return False, msg

    if page.runs is not None:
        if not may_resubmit(page.runs):
            return False, 'Cancelled by user'

    req = submit_request(session, page, file)
    if submit_ok(req):
        return True, 'Success!'
    else:
        return False, get_error_msg(req)
