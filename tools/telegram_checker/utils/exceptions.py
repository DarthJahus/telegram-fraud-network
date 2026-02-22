from inspect import currentframe
from pathlib import Path


class DebugException(Exception):
    """Exception pour le debugging uniquement"""
    def __init__(self, message):
        frame = currentframe().f_back
        self.func_name = frame.f_code.co_name
        self.line_no = frame.f_lineno
        self.file_name = Path(frame.f_code.co_filename).name
        self.line_no_in_func = frame.f_lineno - frame.f_code.co_firstlineno + 1
        super().__init__(message)


class GracefullyExit(DebugException):
    pass
