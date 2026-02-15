#!/usr/bin/env python3
"""
Logging system with multiple levels and file outputs
"""

import sys
import builtins
from enum import Enum


class LogLevel(Enum):
    """Logging levels for different types of messages"""
    ERROR = 'error'
    INFO = 'info'
    OUTPUT = 'output'
    DEBUG = 'debug'


class Logger:
    """Logger with multiple output levels and file handlers"""

    def __init__(self, debug=False, quiet=False):
        """
        Initialize logger

        Args:
            debug: Enable debug logging
            quiet: Suppress OUTPUT on console (still goes to files)
        """
        self.debug_mode = debug
        self.quiet_mode = quiet
        self.log_file = None
        self.error_file = None
        self.output_file = None

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

    def log(self, message, level=LogLevel.INFO, emoji='', end='\n', flush=False):
        """Generic log method"""
        formatted = f"{emoji} {message}" if emoji else message

        if level == LogLevel.ERROR:
            builtins.print(formatted, file=sys.stderr, end=end, flush=flush)
            if self.log_file:
                builtins.print(formatted, file=self.log_file, end=end, flush=flush)
            if self.error_file:
                builtins.print(formatted, file=self.error_file, end=end, flush=flush)

        elif level == LogLevel.INFO:
            builtins.print(formatted, end=end, flush=flush)
            if self.log_file:
                builtins.print(formatted, file=self.log_file, end=end, flush=flush)

        elif level == LogLevel.OUTPUT:
            if not self.quiet_mode:
                builtins.print(formatted, end=end, flush=flush)
            if self.log_file:
                builtins.print(formatted, file=self.log_file, end=end, flush=flush)
            if self.output_file:
                builtins.print(formatted, file=self.output_file, end=end, flush=flush)

        elif level == LogLevel.DEBUG:
            if self.debug_mode:
                builtins.print(f"[DEBUG] {formatted}", file=sys.stderr, end=end, flush=flush)
                if self.log_file:
                    builtins.print(f"[DEBUG] {formatted}", file=self.log_file, end=end, flush=flush)

    def error(self, message = "", emoji='', end='\n', flush=False):
        """Log error message"""
        self.log(message, level=LogLevel.ERROR, emoji=emoji, end=end, flush=flush)

    def info(self, message = "", emoji='', end='\n', flush=False):
        """Log info message"""
        self.log(message, LogLevel.INFO, emoji, end=end, flush=flush)

    def output(self, message = "", end='\n', flush=False):
        """Log output data"""
        self.log(message, LogLevel.OUTPUT, end=end, flush=flush)

    def debug(self, message = "", end='\n', flush=False):
        """Log debug message"""
        self.log(message, LogLevel.DEBUG, end=end, flush=flush)


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
