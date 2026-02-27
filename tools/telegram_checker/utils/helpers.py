import sys
import time
from typing import Callable
from inspect import currentframe
from datetime import datetime, timedelta
from telegram_checker.utils.exceptions import DebugException
from telegram_checker.config.api import SLEEP_BETWEEN_CHECKS
from telegram_checker.config.constants import EMOJI
from telegram_checker.utils.logger import get_logger

LOG = get_logger()


def seconds_to_time(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    return " ".join(f"{v} {u}" for v, u in zip((d, h, m, s), ("d", "h", "min", "s")) if v)


def sleep_with_progress(seconds: int, dest: Callable[[str], None] = print, emoji='', padding=0) -> None:
    now = datetime.now()
    resume_at = now + timedelta(seconds=seconds)

    dest(f"{padding * ' '}{emoji} FloodWait: waiting {seconds_to_time(seconds)}...")

    fmt = "%d/%m %H:%M:%S" if resume_at.date() != now.date() else "%H:%M:%S"
    dest(f"{padding * ' '}{EMOJI['time']} Will resume at ~ {resume_at.strftime(fmt)}")

    bar_width = 60
    # "  [" + bar + "] " + time_text + " remaining   "
    max_time_str = seconds_to_time(seconds)
    line_width = 2 + 1 + bar_width + 2 + len(max_time_str) + len(" remaining   ")
    start = time.monotonic()

    while True:
        elapsed = time.monotonic() - start
        remaining = max(0.0, seconds - elapsed)

        filled = int(bar_width * elapsed / seconds)
        bar = filled * "■" + (bar_width - filled) * "□"

        sys.stdout.write(f"\r  [{bar}] {seconds_to_time(int(remaining))} remaining   ")
        sys.stdout.flush()

        if remaining <= 0:
            break

        time.sleep(min(SLEEP_BETWEEN_CHECKS, remaining))

    sys.stdout.write(f"\r{line_width * ' '}\r")
    sys.stdout.flush()


def get_date_time(get_date=True, get_time=True):
    dt_format = ('%Y-%m-%d' if get_date else '') + (' %H:%M' if get_time else '')
    return datetime.now().strftime(dt_format).strip()


def cut_text(text, limit=120):
    if len(text) > limit:
        return text[:(limit - 3)] + '...'
    return text


def format_console(el):
    if not isinstance(el, str):
        return el
    el = el.replace('\\[[', '').replace('\\]]', '')
    el = el.replace('\\[', '[').replace('\\]', ']')
    return el


def format_file(el):
    if not isinstance(el, str):
        return el
    return el.replace('\\[[', '[[').replace('\\]]', ']]')


def copy_to_clipboard(text):
    try:
        import pyperclip
        pyperclip.copy(text)
    except Exception as e:
        LOG.error(f"Could not copy to clipboard {str(e)}")
        LOG.error("Make sure pyperclip is installed.")
        LOG.error("On Linux, install: xclip or xsel")
        print_debug(e, currentframe().f_code.co_name)


def print_debug(e: Exception, source=None):
    LOG.debug()
    LOG.debug(type(e).__name__)
    if isinstance(e, DebugException):
        LOG.debug(f'from {e.func_name}:{e.line_no_in_func} at {e.file_name}:{e.line_no}')
    elif source:
        LOG.debug(f'from {source}:')
    LOG.debug(str(e))


def parse_time_expression(expr):
    """
    Parses a time expression that can be either a number or a Python expression.

    Args:
        expr (str): Time expression (e.g., "86400" or "24*60*60")

    Returns:
        int: Number of seconds

    Raises:
        ValueError: If the expression is invalid
    """
    try:
        # Try to evaluate as a Python expression (allows "24*60*60")
        result = eval(expr, {"__builtins__": {}}, {})
        if not isinstance(result, (int, float)):
            raise ValueError("Expression must evaluate to a number")
        return int(result)
    except Exception as e:
        raise ValueError(f"Invalid time expression '{expr}': {e}")
