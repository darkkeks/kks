import click
import requests
from bs4 import BeautifulSoup


def ejudge_auth(login, password, group_id, session):
    url = f'https://caos.ejudge.ru/ej/client?contest_id={group_id}'

    page = session.post(url, data={
        'login': login,
        'password': password
    })

    if page.status_code != requests.codes.ok:
        click.secho(f'Failed to authenticate (status code {page.status_code})', err=True, fg='red')

    soup = BeautifulSoup(page.content, 'html.parser')

    if 'Invalid contest' in soup.text or 'invalid contest_id' in soup.text:
        click.secho(f'Invalid contest (group id {group_id})', fg='red', err=True)
        return None

    if 'Permission denied' in soup.text:
        click.secho(f'Permission denied', fg='red', err=True)
        return None

    return {}
