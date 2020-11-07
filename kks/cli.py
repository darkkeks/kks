import click

from kks.cmd.auth import auth


@click.group()
def cli():
    """KoKoS helper tool"""


cli.add_command(auth)
