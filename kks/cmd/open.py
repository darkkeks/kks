import webbrowser

import click

from kks.ejudge import get_contest_url
from kks.util import load_auth_data


@click.command()
def open():
    """Parse and display user standings"""

    auth_data = load_auth_data()
    if auth_data is None:
        click.secho('No auth data found, use "kks auth" to login and save contest id', fg='yellow', err=True)
        return

    url = get_contest_url(auth_data)
    click.secho('Opening ' + click.style(url, fg='green'))
    success = webbrowser.open_new_tab(url)
    if success:
        click.secho('Success!', bold=True)
    else:
        click.secho('Failed :(', fg='red', bold=True)

