from inspect import currentframe
from pathlib import Path


class DebugException(Exception):
    """Exception pour le debugging uniquement"""
    def __init__(self, message, original_exc: BaseException = None):
        frame = currentframe().f_back
        self.func_name = frame.f_code.co_name
        self.line_no = frame.f_lineno
        self.file_name = Path(frame.f_code.co_filename).name
        self.line_no_in_func = frame.f_lineno - frame.f_code.co_firstlineno + 1
        self.original_exc = original_exc
        self.original_type = type(original_exc) if original_exc else None
        self.original_type_name = type(original_exc).__name__ if original_exc else None
        super().__init__(message)


class GracefullyExit(DebugException):
    pass
