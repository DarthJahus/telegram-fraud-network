from telegram_checker.utils.exceptions import DebugException


class TelegramUtilsClientError(DebugException):
    pass


class TelegramReportError(DebugException):
    """Raised when Telegram returns an unexpected result during the report flow."""
    pass

