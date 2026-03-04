from telegram_checker.utils.exceptions import DebugException


class LLMRequestError(DebugException):
    """Raised when the HTTP request to the LLM endpoint fails."""
    pass


class LLMResponseParseError(DebugException):
    """Raised when the LLM response cannot be parsed as valid JSON."""
    pass


class LLMUnexpectedStructureError(DebugException):
    """Raised when the parsed JSON does not have the expected structure."""
    pass
