from telegram_checker.utils.exceptions import DebugException


class ValidationException(DebugException):
    pass


class CanceledByUser(DebugException):
    def __init__(self, message='Canceled by user'):
        super().__init__(message)


class CommandsGetInfoError(DebugException):
    pass


class ReportError(DebugException):
    """Raised when the report command fails unrecoverably (entity resolution, message fetch, etc.)"""
    pass


class ReportLLMError(ReportError):
    """Raised when the LLM is unreachable or returns unrecoverable errors across all messages."""
    pass
