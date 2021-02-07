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

    @classmethod
    def parse(cls, err):
        return cls(err.get('message', 'Unknown error'), err.get('num', cls.UNKNOWN))


class EjudgeFuseError(EjudgeError):
    pass
