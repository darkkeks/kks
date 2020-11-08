import click
import requests

from kks.ejudge import ejudge_auth, AuthData
from kks.util import store_session, save_auth_data, save_links


@click.command(short_help='Authorize and save authentication data to configuration directory')
@click.option('-l', '--login', prompt=True)
@click.password_option('-p', '--password', confirmation_prompt=False)
@click.option('-c', '--contest-id', prompt=True, type=int,
              help='''Ejudge contest id.
              For example, https://caos.ejudge.ru/ej/client?contest_id=133 has contest id 133''')
@click.option('--store-password/--no-store-password', default=True,
              help='''Toggle storing plaintext password in config for auto-login.
              If disabled, only session cookies will be stored.
              Enabled by default.''')
def auth(login, password, contest_id, store_password):
    """Authorize and save authentication data to configuration directory

    \b
    Stored files:
    - config.ini     - contains login, password and group number
    - cookies.pickle - last active ejudge session cookies
    - data.json      - data parsed from ejudge (page urls, for example)"""

    session = requests.session()
    auth_data = AuthData(login, contest_id, password)

    links = ejudge_auth(auth_data, session)
    if links is None:
        return

    click.secho('Successfully logged in', fg='green')

    save_auth_data(auth_data, store_password)
    save_links(links)
    store_session(session)

    click.secho('Successfully saved auth data', fg='green', err=True)
