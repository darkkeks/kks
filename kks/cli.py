import click

from kks.cmd.auth import auth
from kks.cmd.init import init


@click.group()
def cli():
    """KoKoS helper tool"""


cli.add_command(auth)
cli.add_command(init)
