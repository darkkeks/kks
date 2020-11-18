import click

from kks.cmd.auth import auth
from kks.cmd.gen import gen
from kks.cmd.init import init
from kks.cmd.lint import lint
from kks.cmd.run import run
from kks.cmd.sync import sync
from kks.cmd.status import status
from kks.cmd.test import test
from kks.cmd.top import top
from kks.cmd.submit import submit
from kks.cmd.open import open
from kks.cmd.upgrade import upgrade, update


@click.group()
def cli():
    """KoKoS helper tool"""


cli.add_command(auth)
cli.add_command(init)
cli.add_command(run)
cli.add_command(test)
cli.add_command(gen)
cli.add_command(lint)
cli.add_command(sync)
cli.add_command(status)
cli.add_command(top)
cli.add_command(submit)
cli.add_command(open)
cli.add_command(upgrade)
cli.add_command(update)
