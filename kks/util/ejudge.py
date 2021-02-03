import pickle
import re

import click

from kks.ejudge import LinkTypes, AuthData, get_contest_url
from kks.util.common import config_directory, read_config, write_config
from kks.errors import AuthError


def load_auth_data():
    config = read_config()
    if not config.has_section('Auth'):
        return None
    auth = config['Auth']
    if 'login' in auth and 'contest' in auth:
        return AuthData(auth['login'], auth['contest'], auth.get('password', None))
    return None


def save_auth_data(auth_data, store_password=True):
    config = read_config()
    config['Auth'] = {
        'login': auth_data.login,
        'contest': auth_data.contest_id
    }

    if store_password and auth_data.password is not None:
        config['Auth']['password'] = auth_data.password

    write_config(config)


def load_links():
    config = read_config()
    if config.has_section('Links'):
        return config['Links']
    return None


def save_links(links):
    config = read_config()
    config['Links'] = links
    write_config(config)


def load_session():
    import requests

    cookies = config_directory() / 'cookies.pickle'
    if not cookies.is_file():
        return None

    session = requests.session()
    with open(cookies, 'rb') as f:
        try:
            cookies = pickle.load(f)
        except Exception:
            return None
        session.cookies.update(cookies)
    return session


def store_session(session):
    cookies = config_directory() / 'cookies.pickle'
    with open(cookies, 'wb') as f:
        pickle.dump(session.cookies, f)


class EjudgeSession():
    sid_regex = re.compile('/S([0-9a-f]{16})')

    def __init__(self, auth=True):
        import requests
        self.http = load_session()

        if self.http is not None:
            self.links = load_links()

        if self.http is None or self.links is None:
            if auth:
                self.auth()
        else:
            self._update_sid()

    def auth(self, auth_data=None, store_password=None):
        if auth_data is None:
            click.secho('Cookies are either missing or invalid, trying to auth with saved data', fg='yellow', err=True)
            auth_data = load_auth_data()

            if auth_data is not None:
                store_password = True
                if auth_data.password is None:
                    store_password = False
                    auth_data.password = click.prompt('Password', hide_input=True)

        if auth_data is None:
            click.secho('No valid cookies or auth data, please use "kks auth" to log in', fg='yellow', err=True)
            raise AuthError()

        import requests
        from bs4 import BeautifulSoup

        if self.http is None:
            self.http = requests.session()
        else:
            self.http.cookies.clear()
        url = get_contest_url(auth_data)
        page = self.http.post(url, data={
            'login': auth_data.login,
            'password': auth_data.password
        })

        if page.status_code != requests.codes.ok:
            click.secho(f'Failed to authenticate (status code {page.status_code})', err=True, fg='red')
            raise AuthError()

        soup = BeautifulSoup(page.content, 'html.parser')

        if 'Invalid contest' in soup.text or 'invalid contest_id' in soup.text:
            click.secho(f'Invalid contest (contest id {auth_data.contest_id})', fg='red', err=True)
            raise AuthError()

        if 'Permission denied' in soup.text:
            click.secho('Permission denied (invalid username, password or contest id)', fg='red', err=True)
            raise AuthError()

        buttons = soup.find_all('a', {'class': 'menu'}, href=True)

        self.links = {
            button.text: button['href']
            for button in buttons
        }

        if self.links is None:
            click.secho('Auth data is invalid, use "kks auth" to authorize', fg='red', err=True)
            raise AuthError()

        save_auth_data(auth_data, store_password)
        save_links(self.links)
        store_session(self.http)
        self._update_sid()

    def _update_sid(self):
        self.sid = EjudgeSession.sid_regex.search(self.links.get(LinkTypes.SUMMARY)).group(1)

    def modify_url(self, url):
        return re.sub(EjudgeSession.sid_regex, f'/S{self.sid}', url, count=1)

    def _request(self, method, url, *args, **kwargs):
        response = method(url, *args, **kwargs)
        if 'Invalid session' in response.text:
            self.auth()
            url = self.modify_url(url)
            response = method(url, *args, **kwargs)
        return response

    def get(self, url, *args, **kwargs):
        return self._request(self.http.get, url, *args, **kwargs)

    def post(self, url, *args, **kwargs):
        return self._request(self.http.post, url, *args, **kwargs)
