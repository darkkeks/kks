class EjudgeError(Exception):
    pass


class AuthError(EjudgeError):
    def __str__(self):
        if not self.args:
            return 'Auth error'
        return super().__str__()


class APIError(EjudgeError):
    INVALID_RESPONSE = -2
    UNKNOWN = -1

    INVALID_SESSION = 148

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


class EjudgeFuseError(EjudgeError):
    def __init__(self, msg, api_err=None):
        super().__init__(msg)
        self.api_err = api_err

    def __str__(self):
        s = super().__str__()
        if self.api_err is not None:
            s += f' ({self.api_err})'
        return s
