import webbrowser

import click

from kks.util.ejudge import AuthData, Links


@click.command(name='open')
def open_():
    """Open logged in ejudge session in browser"""

    auth_data = AuthData.load_from_config()
    if auth_data is None:
        click.secho(
            'No auth data found, use "kks auth" to login and save contest id',
            fg='red', err=True
        )
        return

    if auth_data.login is None or auth_data.password is None:
        click.secho(
            'No password or login stored, opening contest without logging in',
            fg='yellow', err=True
        )

    url = Links.contest_login(auth_data, include_creds=True)
    click.secho('Opening... ', nl=False)
    success = webbrowser.open_new_tab(url)
    if success:
        click.secho('Success!', bold=True)
    else:
        click.secho('Failed :(', fg='red', bold=True)
