import argparse
from pathlib import Path
from telegram_checker.config.constants import EMOJI
from telegram_checker.config.constants import REGEX_INVITE_LINK_RAW, REGEX_USERNAME_RAW, REGEX_INVITE_HASH
from telegram_checker.commands.exceptions import ValidationException, CanceledByUser
from telegram_checker.utils.logger import get_logger
from pyperclip import paste

LOG = get_logger()
FROM_CLIPBOARD = "__from_clipboard__"


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description='Check Telegram entities status and update markdown files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Project and methodology:\nhttps://github.com/darthjahus/telegram-fraud-network\n_"
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
        nargs='+',
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
        '--md',
        action='store_true',
        help="Used with --get-identifiers: print results as markdown tasks"
    )
    parser.add_argument(
        '--tg-list',
        action='store_true',
        help="Used with --get-identifiers: print results as a Telegram-friendly list"
    )
    parser.add_argument(
        '--active-only',
        action='store_true',
        help="With --get-invites: only print active invites"
    )
    parser.add_argument(
        '--get-identifiers',
        nargs='?',
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
        '--join',
        action='store_true',
        help="When used with --get-identifiers, join groups and channels that are active, and add users to contacts"
    )
    parser.add_argument(
        '--get-info',
        metavar='IDENTIFIER',
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
    parser.add_argument(
        '--sort-size',
        action='store_true',
        help="Sort entities according to their size."
    )
    parser.add_argument(
        '--report',
        type=str,
        metavar='IDENTIFIER',
        default=None,
        help=(
            'Analyze and report messages from a Telegram entity. '
            'Accepts a username (@handle), a numeric ID, or an invite link. '
            'Example: --report @mychannel  or  --report 987968967'
        )
    )
    parser.add_argument(
        '--interactive',
        action='store_true',
        help=(
            'With --report: prompt before sending reports in the 0.70–0.90 '
            'confidence range. Without this flag those messages are either '
            'auto-reported (0.80–0.90) or only logged (0.70–0.80).'
        )
    )
    parser.add_argument(
        '--all-interactive',
        action='store_true',
        help='With --report: prompt before sending reports'
    )
    parser.add_argument(
        '--llm-url',
        type=str,
        default=None,
        metavar='URL',
        dest='llm_url',
        help=(
            'LM Studio / Ollama endpoint for --report. '
            'If not set, you will be prompted at runtime. '
            'Example: http://localhost:1234/api/v1/chat'
        )
    )
    parser.add_argument(
        '--llm-model',
        type=str,
        default=None,
        metavar='MODEL',
        dest='llm_model',
        help=(
            'Model name to pass to the LLM endpoint for --report. '
            'If not set, you will be prompted at runtime. '
            'Example: mistral-nemo'
        )
    )
    parser.add_argument(
        '--update',
        action='store_true',
        help='Used with --report, updates the Telegram report tree from the first analyzed message before reporting',
    )
    parser.add_argument(
        '--update-file',
        help='Update entity file with --report stats'
    )
    parser.add_argument(
        '--yes',
        action='store_true',
        help='Bypass and accept any prompt with a YES (e.g. overwrite files)'
    )
    parser.add_argument(
        '--no',
        action='store_true',
        help='Bypass and reject any prompt with a NO (e.g. overwrite files)'
    )
    parser.add_argument(
        '--mass-report',
        action='store_true',
        help='Report all entities in a folder (use --path)'
    )
    return parser


def validate_args(args):
    if args.no_skip and not (args.get_identifiers and args.invites_only):
        print(f"{EMOJI['warning']} --no-skip can only be used with --get-identifiers --invites-only")
    if args.continuous and not args.get_identifiers:
        print(f"{EMOJI['warning']} --continuous can only be used with --get-identifiers")
    if args.continuous and args.sort_size:
        print(f"{EMOJI['warning']} --continuous cannot be used with --sort-size. Ignoring --continuous")
        args.continuous = False
    if args.md and not (args.get_identifiers or args.report or args.mass_report):
        print(f"{EMOJI['warning']} --md can only be used with --get-identifiers, --report or --mass-report")
    if args.tg_list and not args.get_identifiers:
        print(f"{EMOJI['warning']} --tg-list can only be used with --get-identifiers")
    if args.md and args.tg_list:
        print(f"{EMOJI['warning']} --md-tasks cannot be used with --tg_list. Ignoring --md")
        args.md = False
    if args.active_only and not args.get_identifiers:
        print(f"{EMOJI['warning']} --active-only can only be used with --get-identifiers. Ignoring")
    if args.clean and not args.get_identifiers:
        print(f"{EMOJI['warning']} --clean can only be used with --get-identifiers. Ignoring")
    if args.include_users and not args.get_identifiers:
        print(f"{EMOJI['warning']} --include-users can only be used with --get-identifiers. Ignoring")
    if args.join:
        if not args.get_identifiers:
            print(f"{EMOJI['warning']} --join can only be used with --get-identifiers. Ignoring")
        elif args.get_identifiers == 'all':
            print(f"{EMOJI['warning']} With --get-identifiers all, no validation is done. --join will be ignored")
            args.join = None
        elif not args.user:
            raise ValidationException('--get-identifiers --join needs --user')
    if args.from_clipboard and not args.get_info:
        raise ValidationException('--from-clipboard can only be used with --get-info')
    elif args.from_clipboard and args.get_info != FROM_CLIPBOARD:
        print(f"{EMOJI['warning']} --from-clipboard can only be used with bare --get-info. Ignoring")
    if args.get_info == FROM_CLIPBOARD and not args.from_clipboard:
        raise ValidationException('No identifier has been set for --get-info')
    if args.interactive and not args.report:
        print(f"{EMOJI['warning']} --interactive can only be used with --report")
    if args.all_interactive and not args.report:
        print(f"{EMOJI['warning']} --all-interactive can only be used with --report")
    if args.all_interactive and args.interactive:
        print(f"{EMOJI['warning']} --all-interactive supersedes --interactive")
    if args.llm_url and not (args.report or args.mass_report):
        print(f"{EMOJI['warning']} --llm-url has no effect without --report or --mass-report")
    if args.llm_model and not (args.report or args.mass_report):
        print(f"{EMOJI['warning']} --llm-model has no effect without --report or --mass-report")
    if args.update and not (args.report or args.mass_report):
        print(f"{EMOJI['warning']} --update has no effect without --report or --mass-report")
    if args.report and args.mass_report:
        print(f"{EMOJI['warning']} --report and --mass-report should not be used at the same time")
        if args.path:
            args.report = None  # Suppress --report
            print(f"{EMOJI['info']} --path provided; --mass-report will be kept")
        else:
            args.mass_report = None
            print(f"{EMOJI['info']} no --path provided; --report will be kept")
    if args.mass_report and not args.path:
        raise ValidationException('--path needed for --mass-report')
    if args.update_file and not args.report:
        print(f"{EMOJI['warning']} --update-file has no effect without --report")
        if args.mass_report:
            args.update_file = None
    if args.no and args.yes:
        print(f"{EMOJI['warning']} --yes and --no used at the same time. Assuming --no only.")
        args.yes = False
    if args.mass_report:
        if not args.skip or args.skip == []:
            print(f"{EMOJI['warning']} --mass-report will, by default, use --skip banned unknown")
            args.skip = ["banned", "unknown"]
        if not args.type or args.type == []:
            print(f"{EMOJI['warning']} --mass-report will, by default, use --type group channel bot")
            args.type = ["group", "channel", "bot"]
        if not args.skip_time:
            print(f"{EMOJI['warning']} --mass-report will, by default, use --skip-time 48*60*60 (48 h).")
            args.skip_time = "48*60*60"


    # Validate --get-info options
    if args.get_info:
        if args.get_info == FROM_CLIPBOARD and args.from_clipboard:
            get_info = paste().strip()
            args.no_exit = True
            if not get_info:
                raise ValidationException('Clipboard is empty or contains an empty string.')
            if len(get_info) > 32:
                raise ValidationException('Clipboard content is too large for this operation.')
            args.get_info = get_info
        else:
            get_info = args.get_info.strip()

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
            raise ValidationException(
                "Make sure you use a correct identifier:"
                "  - Invite link: https://t.me/+hlQ3QhNi6q05ZDIx"
                "  - Invite hash: +hlQ3QhNi6q05ZDIx"
                "  - ID: 3456721728"
                "  - Username: @username or username"
            )

    if args.copy and not args.get_info:
        print(f"{EMOJI['warning']} --copy requires --get-info")

    if not args.path and not args.get_info and not args.report:
        raise ValidationException('The following arguments are required: --path')

    # Validate log file paths
    if args.log_full:
        log_path = Path(args.log_full)
        if log_path.exists():
            print(f"{EMOJI['warning']} Log file already exists: {args.log_full}")
            if args.yes:
                print(f"{EMOJI['warning']} --yes: overwriting file…")
                response = 'y'
            elif args.no:
                print(f"{EMOJI['info']} --no: Will not overwrite the file.")
                response = 'n'
            else:
                response = input("Overwrite? (y/N): ").strip().lower()
            if response not in ['y', 'yes']:
                raise CanceledByUser()

    if args.log_error:
        error_path = Path(args.log_error)
        if error_path.exists():
            print(f"{EMOJI['warning']} Error log file already exists: {args.log_error}")
            if args.yes:
                print(f"{EMOJI['warning']} --yes: overwriting file…")
                response = 'y'
            elif args.no:
                print(f"{EMOJI['info']} --no: Will not overwrite the file.")
                response = 'n'
            else:
                response = input("Overwrite? (y/N): ").strip().lower()
            if response not in ['y', 'yes']:
                raise CanceledByUser()

    # Validate --out-file (keep existing validation)
    if args.out_file:
        if Path(args.out_file).exists():
            print(f"\n{EMOJI['warning']} Output file already exists: {args.out_file}")
            if args.yes:
                print(f"{EMOJI['warning']} --yes: overwriting file…")
                response = 'y'
            elif args.no:
                print(f"{EMOJI['info']} --no: Will not overwrite the file.")
                response = 'n'
            else:
                response = input("Overwrite? (y/N): ").strip().lower()
            if response not in ['y', 'yes']:
                raise CanceledByUser()

    if args.update_file:
        if not Path(args.update_file).exists():
            print(f"\n{EMOJI['warning']} File to update does not exist: {args.update_file}")
            args.update_file = None
            if not args.md:
                print(f"{EMOJI['info']} Markdown output enabled; copy the block manually into your file.")
                args.md = True
