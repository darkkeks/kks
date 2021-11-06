import click

from kks.ejudge import AuthData, get_contest_id
from kks.util.ejudge import EjudgeSession, save_auth_data


@click.command(short_help='Authorize and save authentication data to configuration directory')
@click.option('-l', '--login', prompt=True)
@click.password_option('-p', '--password', confirmation_prompt=False)
@click.option('-g', '--group-id',
              help='''2021 group id (e.g. 204, 2010 or 'free' for 'вольнослушатели')''')
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
        group_id = click.prompt("2021 group id (e.g. 204, 2010 or 'free' for 'вольнослушатели')")

    if group_id is not None and contest_id is not None:
        click.secho("Specify either contest id, or group id, not both", fg='red', err=True)
        return

    if contest_id is None:
        contest_id = get_contest_id(group_id)
        if contest_id is None:
            click.secho(
                f"Invalid group id '{group_id}'"
                "(should be either a number from 201 to 2010 or 'free'",
                fg='red', err=True
            )
            return

    session = EjudgeSession(auth=False)
    auth_data = AuthData(login, contest_id, password)

    session.auth(auth_data)
    save_auth_data(auth_data, store_password)

    click.secho('Successfully logged in', fg='green')
    click.secho('Successfully saved auth data', fg='green', err=True)
