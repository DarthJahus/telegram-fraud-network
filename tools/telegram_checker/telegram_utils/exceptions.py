from telegram_checker.utils.exceptions import DebugException


class TelegramUtilsClientError(DebugException):
    pass


class TelegramUtilsReportError(DebugException):
    """Raised when Telegram returns an unexpected result during the report flow."""
    pass


class TelegramUtilsReportNoReport(DebugException):
    """Raised if no report reason is found, nothing to report, not going to report and not asking user"""
    pass


class TelegramUtilsReportSkippedByUser(DebugException):
    """Raised if user decides to skip a report"""
    pass


class TelegramUtilsActionJoinEntityError(DebugException):
    pass


class TelegramUtilsActionAddContactError(DebugException):
    pass
