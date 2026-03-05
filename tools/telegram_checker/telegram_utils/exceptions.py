from telegram_checker.utils.exceptions import DebugException


class TelegramUtilsClientError(DebugException):
    pass


class TelegramReportError(DebugException):
    """Raised when Telegram returns an unexpected result during the report flow."""
    pass

class TelegramReportNoReport(DebugException):
    """Raised if no report reason is found, nothing to report, not going to report and not asking user"""
    pass

class TelegramReportSkippedByUser(DebugException):
    """Raised if user decides to skip a report"""
    pass
