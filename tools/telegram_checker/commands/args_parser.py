import argparse
from pathlib import Path
from telegram_checker.config.constants import EMOJI
from telegram_checker.config.constants import REGEX_INVITE_LINK_RAW, REGEX_USERNAME_RAW, REGEX_INVITE_HASH
from telegram_checker.utils.logger import get_logger
from pyperclip import paste

LOG = get_logger()
FROM_CLIPBOARD = "__from_clipboard__"

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
        nargs='?',
        const=FROM_CLIPBOARD,
        default=None,
        help='Get full information about a Telegram entity and output as MDML'
    )
    parser.add_argument(
        '--copy',
        action='store_true',
        help='Copy --get-info MDML result to clipboard.'
    )
    parser.add_argument(
        "--from-clipboard",
        action="store_true",
        help="With --get-info, retrieve entity identifier from clipboard."
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
    parser.add_argument(
        '--no-exit',
        action='store_true',
        help="Don't exit the program at the end of operations"
    )

    return parser


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
    if args.from_clipboard and not args.get_info:
        print(f"{EMOJI['error']} --from-clipboard can only be used with --get-info")
        if args.no_exit: input('Press any key to exit')
        exit(1)
    elif args.from_clipboard and args.get_info != FROM_CLIPBOARD:
        print(f"{EMOJI['warning']} --from-clipboard can only be used with bare --get-info")
    if args.get_info == FROM_CLIPBOARD and not args.from_clipboard:
        print(f"{EMOJI['error']} No identifier has been set for --get-info")
        if args.no_exit: input('Press any key to exit')
        exit(1)

    # Validate --get-info options
    if args.get_info:
        if args.get_info == FROM_CLIPBOARD and args.from_clipboard:
            get_info = paste().strip()
            args.no_exit = True
            if len(get_info) > 32:
                print(f"{EMOJI['error']} Clipboard content is too large for this operation.")
                input('Press any key to exit')
                exit(2)
            args.get_info = get_info
        else:
            get_info = args.get_info.strip()

        # ToDo: better validate URL, usernames and ID
        if REGEX_INVITE_LINK_RAW.match(get_info):
            # invite link
            pass
        elif REGEX_INVITE_HASH.match(get_info):
            # invite hash
            pass
        elif get_info.isdecimal() and not get_info.startswith('0') and len(get_info) <= 15:
            # UserID
            pass
        elif get_info.startswith('@') and REGEX_USERNAME_RAW.match(get_info[1:]) and '__' not in get_info:
            # Username starting with @
            pass
        elif REGEX_USERNAME_RAW.match(get_info) and '__' not in get_info:
            # Username
            pass
        else:
            print("Make sure you use a correct identifier:")
            print("  - Invite link: https://t.me/+hlQ3QhNi6q05ZDIx")
            print("  - Invite hash: +hlQ3QhNi6q05ZDIx")
            print("  - ID: 3456721728")
            print("  - Username: @username or username")
            if args.no_exit: input('Press any key to exit')
            exit(1)

    if args.copy and not args.get_info:
        print(f"{EMOJI['warning']} --copy requires --get-info")

    if not args.path and not args.get_info:
        print(f"{EMOJI['error']} The following arguments are required: --path")
        if args.no_exit: input('Press any key to exit')
        exit(2)

    # Validate log file paths
    if args.log_full:
        log_path = Path(args.log_full)
        if log_path.exists():
            print(f"{EMOJI['warning']} Log file already exists: {args.log_full}")
            response = input("Overwrite? (y/N): ").strip().lower()
            if response not in ['y', 'yes']:
                print(f"{EMOJI['error']} Cancelled by user")
                if args.no_exit: input('Press any key to exit')
                exit(1)

    if args.log_error:
        error_path = Path(args.log_error)
        if error_path.exists():
            print(f"{EMOJI['warning']} Error log file already exists: {args.log_error}")
            response = input("Overwrite? (y/N): ").strip().lower()
            if response not in ['y', 'yes']:
                print(f"{EMOJI['error']} Cancelled by user")
                if args.no_exit: input('Press any key to exit')
                exit(1)

    # Validate --out-file (keep existing validation)
    if args.out_file:
        if Path(args.out_file).exists():
            print(f"\n{EMOJI['warning']} Output file already exists: {args.out_file}")
            response = input("Overwrite? (y/N): ").strip().lower()
            if response not in ['y', 'yes']:
                print(f"{EMOJI['error']} Script cancelled by user.")
                if args.no_exit: input('Press any key to exit')
                exit(1)
