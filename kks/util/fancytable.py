import os
import sys

import click
from click._compat import isatty


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


class DelimiterRow:
    def __init__(self, char='—', color='white', bold=False):
        self.char = char
        self.color = color
        self.bold = bold

    def value(self, width):
        return click.style(self.char * width, fg=self.color, bold=self.bold)


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
            if isinstance(row, DelimiterRow):
                lines.append(row.value(self.calc_width()))
            else:
                lines.append(' '.join([
                    column.value(row)
                    for column in self.columns
                ]))

        return lines

    def show(self, rows, allow_high_tables=False):
        terminal_width, terminal_height = click.get_terminal_size()
        exceeds_width = self.calc_width() > terminal_width
        exceeds_height = len(rows) > terminal_height

        lines = self.render(rows)
        output = '\n'.join(lines)

        if isatty(sys.stdout) and (exceeds_width or exceeds_height and not allow_high_tables):
            if 'LESS' not in os.environ:
                os.environ['LESS'] = '-S -R'
            click.echo_via_pager(output)
        else:
            click.secho(output)
