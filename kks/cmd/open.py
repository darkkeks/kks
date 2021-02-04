import webbrowser

import click

from kks.ejudge import get_contest_url_with_creds
from kks.util.ejudge import load_auth_data


@click.command(name='open')
def open_():
    """Open logged in ejudge session in browser"""

    auth_data = load_auth_data()
    if auth_data is None:
        click.secho('No auth data found, use "kks auth" to login and save contest id', fg='red', err=True)
        return

    if auth_data.login is None or auth_data.password is None:
        click.secho('No password or login stored, opening contest without logging in', fg='yellow', err=True)

    url = get_contest_url_with_creds(auth_data)
    click.secho('Opening... ', nl=False)
    success = webbrowser.open_new_tab(url)
    if success:
        click.secho('Success!', bold=True)
    else:
        click.secho('Failed :(', fg='red', bold=True)
