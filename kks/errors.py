class EjudgeError(Exception):
    pass


class AuthError(EjudgeError):
    pass


class APIError(EjudgeError):
    INVALID_RESPONSE = -2
    UNKNOWN = -1

    INVALID_SESSION = 148

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code
