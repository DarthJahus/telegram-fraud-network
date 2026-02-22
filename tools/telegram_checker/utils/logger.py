#!/usr/bin/env python3
"""
Logging system with multiple levels and file outputs
"""

import sys
import builtins
from enum import Enum
from random import choice
from telegram_checker.config.constants import EMOJI


class LogLevel(Enum):
    """Logging levels for different types of messages"""
    ERROR = 'error'
    INFO = 'info'
    OUTPUT = 'output'
    DEBUG = 'debug'


class Logger:
    """Logger with multiple output levels and file handlers"""
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, debug=False, quiet=False):
        # Only initialize once
        if not hasattr(self, '_initialized'):
            self.debug_mode = debug
            self.quiet_mode = quiet
            self._initialized = True
            self.log_file = None
            self.error_file = None
            self.output_file = None

    def update_settings(self, debug=None, quiet=None):
        """Update logger settings after initialization"""
        if debug is not None:
            self.debug_mode = debug
        if quiet is not None:
            self.quiet_mode = quiet

    def open_files(self, log_path=None, error_path=None, output_path=None):
        """
        Open log files for writing

        Args:
            log_path: Path for complete log file
            error_path: Path for error log file
            output_path: Path for output file

        Returns:
            bool: True if successful
        """
        try:
            if log_path:
                self.log_file = open(log_path, 'w', encoding='UTF-8')
            if error_path:
                self.error_file = open(error_path, 'w', encoding='UTF-8')
            if output_path:
                self.output_file = open(output_path, 'w', encoding='UTF-8')
            return True
        except Exception as e:
            builtins.print(f"Failed to open log files: {e}", file=sys.stderr)
            return False

    def close_files(self):
        """Close all open log files"""
        if self.log_file:
            self.log_file.close()
            self.log_file = None
        if self.error_file:
            self.error_file.close()
            self.error_file = None
        if self.output_file:
            self.output_file.close()
            self.output_file = None

    @staticmethod
    def _format_console(text):
        """Remove Obsidian escapes for console"""
        if not isinstance(text, str):
            return text
        text = text.replace('\\[[', '').replace('\\]]', '')
        text = text.replace('\\[', '[').replace('\\]', ']')
        return text

    @staticmethod
    def _format_file(text):
        """Keep Obsidian links for file"""
        if not isinstance(text, str):
            return text
        return text.replace('\\[[', '[[').replace('\\]]', ']]')

    def log(self, message, level=LogLevel.INFO, emoji='', padding=0, end='\n', flush=False):
        """Generic log method"""
        padding = padding * ' '
        formatted = f"{padding}{emoji} {message}" if emoji else f"{padding}{message}"

        # Format pour console et fichier
        console_msg = self._format_console(formatted)
        file_msg = self._format_file(formatted)

        if level == LogLevel.ERROR:
            builtins.print(console_msg, file=sys.stderr, end=end, flush=flush)
            if self.log_file:
                builtins.print(file_msg, file=self.log_file, end=end, flush=flush)
            if self.error_file:
                builtins.print(file_msg, file=self.error_file, end=end, flush=flush)

        elif level == LogLevel.INFO:
            builtins.print(console_msg, end=end, flush=flush)
            if self.log_file:
                builtins.print(file_msg, file=self.log_file, end=end, flush=flush)

        elif level == LogLevel.OUTPUT:
            if not self.quiet_mode:
                builtins.print(console_msg, end=end, flush=flush)
            if self.log_file:
                builtins.print(file_msg, file=self.log_file, end=end, flush=flush)
            if self.output_file:
                builtins.print(file_msg, file=self.output_file, end=end, flush=flush)

        elif level == LogLevel.DEBUG:
            # DEBUG does not use emoji and padding
            if self.debug_mode:
                builtins.print(console_msg, file=sys.stderr, end=end, flush=flush)
                if self.log_file:
                    builtins.print(file_msg, file=self.log_file, end=end, flush=flush)

    def error(self, message = "", emoji='', padding=0, end='\n', flush=False):
        """Log error message"""
        self.log(message, level=LogLevel.ERROR, emoji=emoji, padding=padding, end=end, flush=flush)

    def info(self, message = "", emoji='', padding=0, end='\n', flush=False):
        """Log info message"""
        self.log(message, LogLevel.INFO, emoji=emoji, padding=padding, end=end, flush=flush)

    def output(self, message = "", emoji='', padding=0, end='\n', flush=False):
        """Log output data"""
        self.log(message, LogLevel.OUTPUT, emoji=emoji, padding=padding, end=end, flush=flush)

    def debug(self, message = "", padding=0, end='\n', flush=False):
        """Log debug message"""
        self.log(message, LogLevel.DEBUG, emoji=choice(EMOJI["list_bugs"]), padding=padding, end=end, flush=flush)


# Global singleton instance
_logger_instance = None

def get_logger():
    """Get the global logger instance"""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = Logger()
    return _logger_instance

def init_logger(debug=False, quiet=False):
    """Initialize or reconfigure the global logger"""
    logger = get_logger()
    logger.update_settings(debug=debug, quiet=quiet)
    return logger


if __name__ == '__main__':
    """Examples"""
    print("=" * 60)
    print("Logger Module - Usage Examples")
    print("=" * 60)
    print()

    # Create logger instance
    my_logger = Logger(debug=True, quiet=False)
    my_logger.open_files('full.log', 'error.log', 'output.txt')

    # Usage examples
    my_logger.error("This is an error", "❌")
    my_logger.info("This is info", "ℹ️")
    my_logger.output("This is output data")
    my_logger.debug("This is debug info")

    # Test quiet mode
    my_logger.quiet_mode = True
    my_logger.output("This won't show on console")

    my_logger.close_files()
