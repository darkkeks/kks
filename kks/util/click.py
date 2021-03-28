import os
import sys

import click
from click._compat import isatty


class Choice2(click.Choice):
    """ for nice help message """
    def get_metavar(self, param):
        if len(self.choices) == 1:
            return self.choices[0]
        return "[{}]".format("|".join(self.choices))


# classes to create a flag with optional value, see https://stackoverflow.com/a/44144098
# click 8.0 should support something like this (https://github.com/pallets/click/issues/549)
class FlagOption(click.Option):
    """ Mark this option as getting a _opt option """
    is_optflag = True


class OptFlagOption(click.Option):
    """ Fix the help for the _opt suffix """
    def get_help_record(self, ctx):
        help = super().get_help_record(ctx)
        return (help[0].replace('_opt ', '='),) + help[1:]

    def get_error_hint(self, ctx):
        hint = super().get_error_hint(ctx)
        return hint.replace('_opt', '')


class OptFlagCommand(click.Command):
    """ Command with support for flags with values """
    def parse_args(self, ctx, args):
        """ Translate any flag= to flag_opt= as needed """
        options = [o for o in ctx.command.params
                   if getattr(o, 'is_optflag', None)]
        prefixes = {p for p in sum([o.opts for o in options], [])
                    if p.startswith('--')}
        for i, a in enumerate(args):
            a = a.split('=')
            if a[0] in prefixes and len(a) > 1:
                a[0] += '_opt'
                args[i] = '='.join(a)

        return super().parse_args(ctx, args)


class GroupedGroup(click.Group):
    def add_command(self, command, *args, **kwargs):
        help_group = kwargs.pop('group', None)
        command.help_group = help_group
        return super().add_command(command, *args, **kwargs)

    def format_commands(self, ctx, formatter):
        """see https://stackoverflow.com/a/58770064"""
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


class Column:
    def header(self):
        raise NotImplementedError()

    def value(self, row):
        raise NotImplementedError()

    def width(self):
        raise NotImplementedError()


class StaticColumn(Column):
    def __init__(self, name, width, mapper, right_just=True):
        self.name = name
        if self.name is None:
            self.name = ''
        self.mapper = mapper
        self.actual_width = max(width, len(self.name))
        self.right_just = right_just

    def _justify(self, value):
        return value.rjust(self.actual_width, ' ') if self.right_just \
            else value.ljust(self.actual_width, ' ')

    def header(self):
        return click.style(self._justify(self.name), fg='white', bold=True)

    def value(self, row):
        return click.style(self._justify(str(self.mapper(row))), fg=row.color(), bold=row.bold())

    def width(self):
        return self.actual_width

    @classmethod
    def padding(cls, width):
        # width - 1, так как лишняя колонка уже добавляет один пробел
        return cls(None, width - 1, lambda _: '')


class FancyTable:
    def __init__(self):
        self.columns = []

    def add_column(self, column):
        self.columns.append(column)

    def calc_width(self):
        content = sum([column.width() for column in self.columns])
        return content + len(self.columns) - 1

    def render(self, rows):
        lines = [
            ' '.join([
                column.header()
                for column in self.columns
            ])
        ]

        for row in rows:
            lines.append(' '.join([
                column.value(row)
                for column in self.columns
            ]))

        return lines

    def show(self, rows, force_pager=False):
        terminal_width, _ = click.get_terminal_size()
        exceeds_width = self.calc_width() > terminal_width

        lines = self.render(rows)
        output = '\n'.join(lines)

        if isatty(sys.stdout) and (exceeds_width or force_pager):
            if 'LESS' not in os.environ:
                os.environ['LESS'] = '-S -R'
            click.echo_via_pager(output)
        else:
            click.secho(output)

