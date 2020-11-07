import click
import requests

from kks.ejudge import ejudge_auth
from kks.util import read_config, write_config, store_session


@click.command(short_help='Authorize and save authentication data to configuration directory')
@click.option('-l', '--login', prompt=True)
@click.password_option('-p', '--password', confirmation_prompt=False)
@click.option('-g', '--group-id', prompt=True, type=int,
              help='''Ejudge contest id.
              For example, https://caos.ejudge.ru/ej/client?contest_id=133 has contest id 133''')
@click.option('--store-password/--no-store-password', default=True,
              help='''Toggle storing plaintext password in config for auto-login.
              If disabled, only session cookies will be stored.
              Enabled by default.''')
def auth(login, password, group_id, store_password):
    """Authorize and save authentication data to configuration directory

    \b
    Stored files:
    - config.ini     - contains login, password and group number
    - cookies.pickle - last active ejudge session cookies
    - data.json      - data parsed from ejudge (page urls, for example)"""

    session = requests.session()
    data = ejudge_auth(login, password, group_id, session)

    if data is None:
        click.secho('Failed to authenticate (invalid username, password or group id)', fg='red', err=True)
        return

    click.secho('Successfully logged in', fg='green')

    config = read_config()
    config['Auth'] = {
        'login': login,
        'group': group_id
    }

    if store_password:
        config['Auth']['password'] = password

    write_config(config)
    store_session(session)

    click.secho('Successfully saved auth data', fg='green')
