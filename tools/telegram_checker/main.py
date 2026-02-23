#!/usr/bin/env python3
"""
Telegram Entities Status Checker
Checks the status of Telegram entities (channels, groups, users, bots) and updates markdown files.

Usage:
  python check_status_tg.py --path . --type all [--dry-run]
  python check_status_tg.py --path . --skip-time 86400 --skip unknown banned
  python check_status_tg.py --path . --skip-time "24*60*60"

ToDo: Can we consider using more than 1 account at the same time,
      and check with every account before settling on a status?
      Should reveal helpful for groups where one account has been accepted,
      and that others can't access.
ToDo: For --get-identifiers, add:
      --only-tags tag1,tag2,...
"""

# Imports

## General imports
from pathlib import Path

## Telegram-Checker
from telegram_checker.config.constants import EMOJI
from telegram_checker.utils.exceptions import GracefullyExit
from telegram_checker.utils.helpers import copy_to_clipboard, parse_time_expression, print_debug
from telegram_checker.telegram_utils.client import connect_to_telegram
from telegram_checker.commands.full_check import full_check
from telegram_checker.commands.list_identifiers import list_identifiers
from telegram_checker.commands.get_entity_info import get_entity_info
from telegram_checker.commands.args_parser import build_arg_parser, validate_args
from telegram_checker.commands.exceptions import ValidationException, CanceledByUser
from telegram_checker.utils.logger import init_logger


def main():
    args = build_arg_parser().parse_args()

    try:
        validate_args(args)
    except ValidationException as e:
        print(f'{EMOJI['error']} {str(e)}')
        input('Press any key to exit')
        exit(1)
    except CanceledByUser as e:
        print(f'{EMOJI['info']} {str(e)}')
        input('Press any key to exit')
        exit(2)

    try:
        # logging
        log = init_logger(debug=args.verbose, quiet=args.quiet)
    except Exception as e:
        print(f'{EMOJI['info']} {str(e)}')
        input('Press any key to exit')
        exit(3)

    try:
        # Open log files if specified
        if args.log_full or args.log_error or args.out_file:
            log.open_files(
                log_path=args.log_full if hasattr(args, 'log_full') else None,
                error_path=args.log_error if hasattr(args, 'log_error') else None,
                output_path=args.out_file if hasattr(args, 'out_file') else None
            )

        # Handle --get-info mode
        if args.get_info:
            client = connect_to_telegram(args.user)
            try:
                entity_info = get_entity_info(
                    client,
                    identifier=args.get_info
                )
                log.output(str(entity_info))
                if args.copy:
                    copy_to_clipboard(entity_info)
                    log.info(f"{EMOJI['reason']} Copied to clipboard!")
            finally:
                client.disconnect()
            raise GracefullyExit('Done with the entity!')

        # Parse skip-time if provided
        skip_time_seconds = None
        if args.skip_time:
            skip_time_seconds = parse_time_expression(args.skip_time)
            hours = skip_time_seconds / 3600
            log.info(f"Skip time: {skip_time_seconds}s ({hours:.1f} hours)", EMOJI["time"])

        # Parse skip statuses
        if args.skip:
            log.info(f"Skip statuses: {', '.join(args.skip)}", EMOJI["skip"])

        # Parse ignore statuses
        ignore_statuses = args.ignore if args.ignore else None
        if ignore_statuses:
            log.info(f"Ignore statuses: {', '.join(ignore_statuses)}", EMOJI["ignored"])

        # Parse no-skip-unknown
        if args.no_skip_unknown:
            log.info(f"{EMOJI["info"]} {EMOJI["file"]} with {EMOJI["unknown"]} status will be checked")

        # Find all .md files
        path = Path(args.path)
        if not path.exists():
            raise ValidationException(f'Path does not exist: {path}')

        md_files = list(path.glob('*.md'))

        if not md_files:
            raise ValidationException(f'No .md files found in {path}')

        log.info(f"{len(md_files)} .md files found", EMOJI["folder"])
        log.info(f"Filter: {args.type}", emoji='🔍')
        if args.dry_run:
            log.info(f"Mode: DRY-RUN (no file modifications)", emoji='🔎')
        log.info()

        # Connect to Telegram
        client = None
        if not (args.get_identifiers == 'all'):
            client = connect_to_telegram(args.user)

        # Handle --get-identifiers mode without connection if mode is 'all'
        if args.get_identifiers:
            list_identifiers(
                client,
                md_files,
                args
            )
            if client:
                client.disconnect()
            raise GracefullyExit('Done with the identifiers!')

        full_check(client, args, ignore_statuses, md_files, skip_time_seconds)
        raise GracefullyExit('Done with the full check!')

    except GracefullyExit as e:
        if str(e):
            print(f"\n{EMOJI["info"]} {str(e)}")
        exit(0)

    except Exception as e:
        print_debug(e, 'main()')
        input('Press any key to exit.')
        exit(3)


if __name__ == '__main__':
    main()
