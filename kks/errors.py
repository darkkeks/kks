import click
from click.exceptions import ClickException

from kks.util.common import format_file


class EjudgeError(ClickException):
    def __init__(self, message='unknown error'):
        super().__init__(message)


class ParseError(EjudgeError):
    pass


class EjudgeUnavailableError(EjudgeError):
    def __init__(self, message='Ejudge is not available'):
        super().__init__(message)


class AuthError(EjudgeError):
    def __init__(self, message='Auth error', fg='red'):
        super().__init__(message)
        self.fg = fg

    def show(self):
        click.secho(self.message, fg=self.fg, err=True)


class DefaultPasswordError(AuthError):
    message = click.style(
        'Your account has a default password.\n'
        'Change your password via Web UI and rerun "kks auth" or edit ', fg='red'
    ) + format_file('~/.kks/config.ini') + click.style(' manually.', fg='red')

    def __init__(self):
        super().__init__(self.message)

    def show(self):
        click.echo(self.message, err=True)


class APIError(EjudgeError):
    INVALID_RESPONSE = -2
    UNKNOWN = -1

    INVALID_SESSION = 148

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code
