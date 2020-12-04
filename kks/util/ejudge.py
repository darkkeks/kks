import json
import pickle
import re
from collections import namedtuple

import click

from kks import __version__
from kks.ejudge import LinkTypes, AuthData, get_contest_url
from kks.util.common import config_directory, read_config, write_config
from kks.errors import AuthError, APIError


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


class RunStatus:
    COMPILING = 98  # from github.com/blackav/ejudge-fuse
    COMPILED = 97
    RUNNING = 96

    OK = 0
    CE = 1
    RE = 2
    TL = 3
    PE = 4
    WA = 5
    ML = 12

    CHECK_FAILED = 6
    PARTIAL = 7
    ACCEPTED = 8
    IGNORED = 9
    PENDING = 11

    PENDING_REVIEW = 16
    REJECTED = 17

    @staticmethod
    def is_testing(status):
        return status >= 95 and status <= 99


class API:
    class AuthData:
        def __init__(self, ejsid, sid):
            self.ejsid = ejsid
            self.sid = sid

    def __init__(self, auth_data=None):
        import requests

        self._prefix = 'https://caos.ejudge.ru/cgi-bin/'
        self._http = requests.Session()
        self._http.headers = {'User-Agent': f'kokos/{__version__}'}

        self.auth_data = auth_data

    def _request(self, path, action, auth_data=None, decode=True, **kwargs):
        """
        Allowed values for `auth_data`:
          - None (use self.auth_data)
          - False (don't use sids)
          - API.AuthData(ejsid, sid)
        """

        url = self._prefix + path

        data = kwargs.pop('data', {})
        data['action'] = action
        data['json'] = 1
        if auth_data:
            data['EJSID'], data['SID'] = auth_data.ejsid, auth_data.sid
        elif auth_data is None:
            data['EJSID'], data['SID'] = self.auth_data.ejsid, self.auth_data.sid

        resp = self._http.post(url, data=data, **kwargs)  # all methods accept POST requests
        resp.encoding = 'utf-8'  # ejudge doesn't set encoding header

        if decode:
            try:
                data = json.loads(resp.content)
            except Exception as e:
                raise APIError(f'Invalid response. resp={resp.content}, err={e}', -1)
            if not data['ok']:
                err = data['error']
                raise APIError(err.get('message', 'Unknown error'), err.get('num', -1))
            return data['result']
        return resp.content

    def auth(self, creds):
        """get new sids"""
        # NOTE is 1step auth possible?
        data = {
            'login': creds.login,
            'password': creds.password,
        }
        auth_data = self._request('register', 'login-json', False, data=data)

        data = {
            'contest_id': creds.contest_id
        }
        auth_data = self._request('register', 'enter-contest-json', (auth_data['EJSID'], auth_data['SID']), data=data)
        self.auth_data = API.AuthData(auth_data['EJSID'], auth_data['SID'])

    def contest_status(self):
        return self._request('client', 'contest-status-json')

    def problem_status(self, prob_id):
        data = {
            'problem': int(prob_id)
        }
        return self._request('client', 'problem-status-json', data=data)

    def problem_statement(self, prob_id):
        data = {
            'problem': int(prob_id)
        }
        return self._request('client', 'problem-statement-json', data=data, decode=False)

    def list_runs(self, prob_id):
        # newest runs go first
        # if no prob_id is passed then all runs are returned (useful for sync?)
        if prob_id is not None:
            data = {
                'prob_id': int(prob_id)
            }
            return self._request('client', 'list-runs-json', data=data)['runs']
        return self._request('client', 'list-runs-json')['runs']

    def run_status(self, run_id):
        data = {
            'run_id': int(run_id)
        }
        return self._request('client', 'run-status-json', data=data)

    def download_run(self, run_id):
        data = {
            'run_id': int(run_id)
        }
        return self._request('client', 'download-run', data=data, decode=False)

    def run_messages(self, run_id):
        data = {
            'run_id': int(run_id)
        }
        return self._request('client', 'run-messages-json', data=data)

    # run-test-json - test results? unknown params

    def submit(self, prob_id, file, lang):
        data = {
            'prob_id': int(prob_id),
        }
        if lang is not None:  # NOTE may possibly break on problems without lang (see sm01-3)
            data['lang_id'] = int(lang)

        files = {
            'file': (file.name, open(file, 'rb'))
        }
        return self._request('client', 'submit-run', data=data, files=files)


class EjudgeSession():
    sid_regex = re.compile('/S([0-9a-f]{16})')

    def __init__(self, auth=True):
        self._api_auth_data = API.AuthData(None, None)

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

    def api(self):
        """
        Create an API wrapper with (EJ)SID from this session
        If cookies are outdated, api requests will raise an APIError
        if api is used before any session requests are performed, the caller must handle possible errors
        Example:
        >>> api = session.api()
        >>> try:
        >>>     info = api.contest_status()
        >>> except APIError:
        >>>     session.auth()
        >>>     info = api.contest_status()
        """
        return API(self._api_auth_data)

    def _update_sid(self):
        self._sid = EjudgeSession.sid_regex.search(self.links.get(LinkTypes.SUMMARY)).group(1)
        self._api_auth_data.ejsid = self.http.cookies['EJSID']
        self._api_auth_data.sid = self._sid

    def modify_url(self, url):
        return re.sub(EjudgeSession.sid_regex, f'/S{self._sid}', url, count=1)

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
