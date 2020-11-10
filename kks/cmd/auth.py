import click
import requests

from kks.ejudge import ejudge_auth, AuthData, get_contest_id
from kks.util import store_session, save_auth_data, save_links


@click.command(short_help='Authorize and save authentication data to configuration directory')
@click.option('-l', '--login', prompt=True)
@click.password_option('-p', '--password', confirmation_prompt=False)
@click.option('-g', '--group-id', type=int,
              help='''2020 group id (for example, 193)''')
@click.option('-c', '--contest-id', type=int,
              help='''Ejudge contest id.
              For example, https://caos.ejudge.ru/ej/client?contest_id=133 has contest id 133''')
@click.option('--store-password/--no-store-password', default=True,
              help='''Toggle storing plaintext password in config for auto-login.
              If disabled, only session cookies will be stored.
              Enabled by default.''')
def auth(login, password, group_id, contest_id, store_password):
    """Authorize and save authentication data to configuration directory

    \b
    Stored files:
    - config.ini     - contains login, password and group number
    - cookies.pickle - last active ejudge session cookies
    - data.json      - data parsed from ejudge (page urls, for example)"""

    if group_id is None and contest_id is None:
        group_id = click.prompt("Group Id (e.g. 193)", type=int)

    if group_id is not None and contest_id is not None:
        click.secho("Specify either contest id, or group id, not both", fg='red', err=True)
        return

    if contest_id is None:
        contest_id = get_contest_id(group_id)
        if contest_id is None:
            click.secho(f'Invalid group id "{group_id}" (should be between 191 and 1911)', fg='red', err=True)
            return

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
