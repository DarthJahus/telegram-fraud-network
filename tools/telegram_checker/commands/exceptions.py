from telegram_checker.utils.exceptions import DebugException


class ValidationException(DebugException):
    pass


class CanceledByUser(DebugException):
    def __init__(self, message='Canceled by user'):
        super().__init__(message)


class CommandsGetInfoError(DebugException):
    pass
