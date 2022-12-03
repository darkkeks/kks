import click

from kks.cmd.build import build
from kks.util.click import GroupedGroup
from kks.util.common import config_directory
from kks.cmd.auth import auth
from kks.cmd.convert import convert
from kks.cmd.deadlines import deadlines
from kks.cmd.gen import gen
from kks.cmd.get import get
from kks.cmd.hide import hide, unhide
from kks.cmd.init import init
from kks.cmd.lint import lint
from kks.cmd.open import open_
from kks.cmd.run import run
from kks.cmd.status import status
from kks.cmd.submit import submit
from kks.cmd.sync import sync
from kks.cmd.test import test_
from kks.cmd.top import top
from kks.cmd.upgrade import upgrade, update


def cleanup():
    for filename in ['storage.pickle']:
        file = config_directory() / filename
        if file.exists():
            file.unlink()


@click.group(cls=GroupedGroup)
def cli():
    """KoKoS helper tool"""
    cleanup()


class Commands:
    workspace = ('Workspace-related', 1)
    ejudge = ('Ejudge interaction', 2)
    solution = ('Solution testing', 3)
    other = ('Other', 4)


cli.add_command(init, group=Commands.workspace)
cli.add_command(sync, group=Commands.workspace)
cli.add_command(hide, group=Commands.workspace)
cli.add_command(unhide, group=Commands.workspace)

cli.add_command(auth, group=Commands.ejudge)
cli.add_command(open_, group=Commands.ejudge)
cli.add_command(status, group=Commands.ejudge)
cli.add_command(top, group=Commands.ejudge)
cli.add_command(deadlines, group=Commands.ejudge)
cli.add_command(submit, group=Commands.ejudge)
cli.add_command(get, group=Commands.ejudge)

cli.add_command(lint, group=Commands.solution)
cli.add_command(build, group=Commands.solution)
cli.add_command(run, group=Commands.solution)
cli.add_command(gen, group=Commands.solution)
cli.add_command(test_, group=Commands.solution)

cli.add_command(convert, group=Commands.other)
cli.add_command(upgrade, group=Commands.other)
cli.add_command(update, group=Commands.other)
