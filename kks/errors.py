import click
from click.exceptions import ClickException


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


class APIError(EjudgeError):
    INVALID_RESPONSE = -2
    UNKNOWN = -1

    INVALID_SESSION = 148

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code
