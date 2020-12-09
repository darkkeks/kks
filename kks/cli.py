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
from kks.cmd.hide import hide, unhide
from kks.cmd.upgrade import upgrade, update


class GroupedGroup(click.Group):
    def add_command(self, command, *args, **kwargs):
        help_group = kwargs.pop('group', None)
        command.help_group = help_group
        return super().add_command(command, *args, **kwargs)

    def format_commands(self, ctx, formatter):
        """see stackoverflow.com/a/58770064"""
        commands = []
        for subcommand in self.list_commands(ctx):
            cmd = self.get_command(ctx, subcommand)
            if not (cmd is None or cmd.hidden):
                commands.append((subcommand, cmd))

        if commands:
            longest = max(len(cmd[0]) for cmd in commands)
            limit = formatter.width - 6 - longest

            groups = {}
            for subcommand, cmd in commands:
                help_str = cmd.get_short_help_str(limit)
                subcommand += ' ' * (longest - len(subcommand))
                groups.setdefault(cmd.help_group, []).append((subcommand, help_str))

            with formatter.section('Commands'):
                for (group_name, _), rows in sorted(groups.items(), key=lambda x: x[0][1]):
                    formatter.write_heading(group_name)
                    with formatter.indentation():
                        formatter.write_dl(rows)
                        formatter.write_paragraph()


@click.group(cls=GroupedGroup)
def cli():
    """KoKoS helper tool"""


class Commands:
    ws = ('Workspace-related', 1)
    ej = ('Ejudge interaction', 2)
    bin = ('Binary testing', 3)
    other = ('Other', 4)


cli.add_command(init, group=Commands.ws)
cli.add_command(sync, group=Commands.ws)
cli.add_command(hide, group=Commands.ws)
cli.add_command(unhide, group=Commands.ws)

cli.add_command(auth, group=Commands.ej)
cli.add_command(open, group=Commands.ej)
cli.add_command(status, group=Commands.ej)
cli.add_command(top, group=Commands.ej)
cli.add_command(submit, group=Commands.ej)

cli.add_command(lint, group=Commands.bin)
cli.add_command(run, group=Commands.bin)
cli.add_command(gen, group=Commands.bin)
cli.add_command(test, group=Commands.bin)

cli.add_command(upgrade, group=Commands.other)
cli.add_command(update, group=Commands.other)
