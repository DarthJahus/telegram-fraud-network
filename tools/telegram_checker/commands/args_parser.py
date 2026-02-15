import argparse
from telegram_checker.utils.logger import get_logger
LOG = get_logger()


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description='Check Telegram entities status and update markdown files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
    Examples:
      # Check all entities
      %(prog)s --path .

      # Skip entities checked in the last 24 hours
      %(prog)s --path . --skip-time 86400
      %(prog)s --path . --skip-time "24*60*60"

      # Skip entities with 'unknown' or 'banned' status
      %(prog)s --path . --skip unknown banned

      # Combine both: skip if checked recently OR if unknown/banned
      %(prog)s --path . --skip-time "24*60*60" --skip unknown banned

      # Check only channels, skip those checked in the last 12 hours
      %(prog)s --path . --type channel --skip-time "12*60*60"

      # Check all but don't update files for 'unknown' status
      %(prog)s --path . --ignore unknown

      # Check all but ignore both 'unknown' and 'banned'
      %(prog)s --path . --ignore unknown banned
            """
    )
    parser.add_argument(
        '--user',
        type=str,
        default='default',
        help='User session name (default: default). Session stored in .secret/<user>.session'
    )
    parser.add_argument(
        '--path',
        help='Path to directory containing .md files'
    )
    parser.add_argument(
        '--type',
        choices=['all', 'channel', 'group', 'user', 'bot'],
        default='all',
        help='Filter by entity type (default: all)'
    )
    parser.add_argument(
        '--skip-time',
        type=str,
        metavar='SECONDS',
        help='Skip entities checked within this many seconds (e.g., 86400 or "24*60*60" for 1 day)'
    )
    parser.add_argument(
        '--skip',
        nargs='+',
        metavar='STATUS',
        help='Skip entities with these last statuses (e.g., unknown banned)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Check status without updating .md files'
    )
    parser.add_argument(
        '--ignore',
        nargs='+',
        metavar='STATUS',
        help='Check entities but ignore file updates for these statuses (e.g., unknown banned)'
    )
    parser.add_argument(
        '--no-skip-unknown',
        action='store_true',
        help="Don't skip entities whose last status is 'unknown'"
    )
    parser.add_argument(
        '--out-file',
        help="Output log to a file"
    )
    parser.add_argument(
        '--write-id',
        action='store_true',
        help="Write recovered IDs to markdown files (only for IDs recovered via invite links)"
    )
    parser.add_argument(
        '--no-skip',
        action='store_true',
        help="With --get-invites: don't skip files with 'banned' or 'unknown' status (default: skip them)"
    )
    parser.add_argument(
        '--continuous',
        action='store_true',
        help="With --get-invites: print results continuously (default: print at the end of the process)"
    )
    parser.add_argument(
        '--md-tasks',
        action='store_true',
        help="With --get-invites: print results as markdown tasks"
    )
    parser.add_argument(
        '--valid-only',
        action='store_true',
        help="With --get-invites: only print valid invites"
    )
    parser.add_argument(
        '--get-identifiers',
        nargs='?',
        const='all',
        choices=['all', 'valid'],
        help='List all identifiers (invites + valid handles) (all = non-strikethrough, valid = tested with UserID)'
    )
    parser.add_argument(
        '--invites-only',
        action='store_true',
        help='When used with --get-identifiers, only show invites (skip handles)'
    )
    parser.add_argument(
        '--clean',
        action='store_true',
        help='When used with --get-identifiers, only prints identifiers (no ID, no status)'
    )
    parser.add_argument(
        '--include-users',
        action='store_true',
        help="When used with --get-identifiers, include entities whose type is 'user'"
    )
    parser.add_argument(
        '--get-info',
        action='store_true',
        help='Get full information about a Telegram entity and output as MDML'
    )
    parser.add_argument(
        '--by-id',
        type=int,
        metavar='ID',
        help='Entity ID to retrieve information for (use with --get-info)'
    )
    parser.add_argument(
        '--by-username',
        type=str,
        metavar='USERNAME',
        help='Username to retrieve information for (use with --get-info, without @)'
    )
    parser.add_argument(
        '--by-invite',
        type=str,
        metavar='HASH',
        help='Invite hash to retrieve information for (use with --get-info)'
    )
    parser.add_argument(
        '--copy',
        action='store_true',
        help='Copy --get-info MDML result to clipboard.'
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress OUTPUT from console (still goes to --out-file if specified)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show DEBUG messages on console'
    )
    parser.add_argument(
        '--log-full',
        type=str,
        metavar='FILE',
        help='Log everything (INFO, ERROR, OUTPUT, DEBUG) to file'
    )
    parser.add_argument(
        '--log-error',
        type=str,
        metavar='FILE',
        help='Log errors only to file'
    )

    return parser

from pathlib import Path
from telegram_checker.config.constants import EMOJI


def validate_args(args):
    if args.no_skip and not (args.get_identifiers and args.invites_only):
        print(f"{EMOJI['warning']} --no-skip can only be used with --get-identifiers --invites-only")
    if args.continuous and not args.get_identifiers:
        print(f"{EMOJI['warning']} --continuous can only be used with --get-identifiers")
    if args.md_tasks and not args.get_identifiers:
        print(f"{EMOJI['warning']} --md-tasks can only be used with --get-identifiers")
    if args.valid_only and not args.get_identifiers:
        print(f"{EMOJI['warning']} --valid-only can only be used with --get-identifiers")
    if args.clean and not args.get_identifiers:
        print(f"{EMOJI['warning']} --clean can only be used with --get-identifiers")
    if args.include_users and not args.get_identifiers:
        print(f"{EMOJI['warning']} --include-users can only be used with --get-identifiers")

    # Validate --get-info options
    if args.get_info:
        selectors = sum([bool(args.by_id), bool(args.by_username), bool(args.by_invite)])
        if selectors == 0:
            print(f"{EMOJI['error']} --get-info requires one of: --by-id, --by-username, or --by-invite")
            exit(1)
        elif selectors > 1:
            print(f"{EMOJI['error']} --get-info can only use one selector at a time")
            exit(1)

    if any([args.by_id, args.by_username, args.by_invite, args.copy]) and not args.get_info:
        print(f"{EMOJI['warning']} --by-id, --by-username, --by-invite and --copy require --get-info")

    if not args.path and not args.get_info:
        print(f"{EMOJI['error']} The following arguments are required: --path")
        exit(2)

    # Validate log file paths
    if args.log_full:
        log_path = Path(args.log_full)
        if log_path.exists():
            print(f"{EMOJI['warning']} Log file already exists: {args.log_full}")
            response = input("Overwrite? (y/n): ").strip().lower()
            if response not in ['y', 'yes']:
                print(f"{EMOJI['error']} Cancelled by user")
                exit(1)

    if args.log_error:
        error_path = Path(args.log_error)
        if error_path.exists():
            print(f"{EMOJI['warning']} Error log file already exists: {args.log_error}")
            response = input("Overwrite? (y/n): ").strip().lower()
            if response not in ['y', 'yes']:
                print(f"{EMOJI['error']} Cancelled by user")
                exit(1)

    # Validate --out-file (keep existing validation)
    if args.out_file:
        if Path(args.out_file).exists():
            print(f"\n{EMOJI['warning']} Output file already exists: {args.out_file}")
            response = input("Overwrite? (y/n): ").strip().lower()
            if response not in ['y', 'yes']:
                print(f"{EMOJI['error']} Script cancelled by user.")
                exit(1)
