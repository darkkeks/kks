import click

from kks.ejudge import get_contest_id
from kks.util.ejudge import AuthData, EjudgeSession


GROUP_ID_HINT = "2022 group id (e.g. 214, 2110)"


@click.command(short_help='Authorize and save authentication data to configuration directory')
@click.option('-l', '--login', prompt=True)
@click.password_option('-p', '--password', confirmation_prompt=False)
@click.option('-g', '--group-id', help=GROUP_ID_HINT)
@click.option('-c', '--contest-id', type=int,
              help='''Ejudge contest id.
              For example, https://caos.myltsev.ru/cgi-bin/new-client?contest_id=133 has contest id 133''')
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
        group_id = click.prompt(GROUP_ID_HINT)

    if group_id is not None and contest_id is not None:
        click.secho("Specify either contest id, or group id, not both", fg='red', err=True)
        return

    if contest_id is None:
        contest_id = get_contest_id(group_id)
        if contest_id is None:
            click.secho(
                f"Invalid group id '{group_id}'"
                "(should be a number from 211 to 2110)",
                fg='red', err=True
            )
            return

    auth_data = AuthData(login, password, contest_id)
    # Use new auth data instead of saved
    session = EjudgeSession(auth_data=auth_data, auth=False)
    # (re)auth even if there is a saved session state
    session.auth()

    auth_data.save_to_config(store_password)

    click.secho('Successfully logged in', fg='green')
    click.secho('Successfully saved auth data', fg='green', err=True)
