from inspect import currentframe
from time import sleep
from telegram_checker.utils.logger import get_logger
from telegram_checker.config.constants import EMOJI, UI_HORIZONTAL_LINE
from telegram_checker.config.api import SLEEP_BETWEEN_CHECKS
from telegram_mdml.telegram_mdml import TelegramEntity
from telegram_mdml.telegram_mdml import (
    MissingFieldError,
    InvalidTypeError
)
from telegram_checker.mdml_utils.mdml_parser import get_last_status
from telegram_checker.telegram_utils.validators import validate_invite, validate_handle
from telegram_checker.utils.helpers import print_debug

LOG = get_logger()
# Bins: (label, min_exclusive, max_inclusive)
# None as max_inclusive means +inf
SIZE_BINS = [
    (']   0,   30]',    0,   30),
    (']  30,  100]',   30,  100),
    ('] 100,  200]',  100,  200),
    ('] 200,  500]',  200,  500),
    ('] 500, 1k  ]',  500, 1000),
    (']1k  , 2k  ]', 1000, 2000),
    (']2k  , 3k  ]', 2000, 3000),
    (']3k  , +∞  [', 3000, None),
]


def get_size_bin_label(size):
    """Return the bin label for a given member count. Returns None if count is None."""
    if size is None:
        return None
    for label, low, high in SIZE_BINS:
        if size > low and (high is None or size <= high):
            return label
    return None


def print_identifiers(identifiers_list, md_tasks=False, active_only=False, clean=False, tg_list=False, show_size=False, dest=LOG.output):
    if not identifiers_list:
        return

    n = 0
    md_check_list = ''
    bin_length_digits = 0
    if md_tasks:
        md_check_list = '- [ ] '
    if tg_list:
        valid_count = sum(1 for i in identifiers_list if i['valid'] is True)
        bin_length_digits = len(str(valid_count))
    max_member_count_digits = 0
    if show_size:
        max_member_count_digits = len(str(max(i['member_count'] for i in identifiers_list)))

    for ident in identifiers_list:
        type_indicator = ' ' + (EMOJI['invite'] if "+" in ident['full_link'] else EMOJI['handle'])
        size = '' if not show_size else f" {'| ' if tg_list and active_only else ''}{ident['member_count']:>{max_member_count_digits}} "
        if ident['valid'] is True:
            n += 1
            if tg_list and active_only:
                # TG list is only relevant for valid identifiers
                dest(f"` {n:>{bin_length_digits}} {size}|` {ident['full_link']}")
            else:
                dest(f"{md_check_list}{size}{EMOJI["active"]}{type_indicator} {ident['full_link']}")
            if not clean:
                if ident['user_id']:
                    dest(f"  {EMOJI["id"]      } {ident['user_id']}")
                dest(f"  {EMOJI["file"]    } {ident['file']}")
                dest()
        elif ident['valid'] is False and not active_only:
            dest(f"{md_check_list}{size}{EMOJI["no_emoji"]}{type_indicator} {ident['full_link']}")
            if not clean:
                dest(f"  {EMOJI["file"]    } {ident['file']}")
                dest(f"  {EMOJI["text"]    } {ident['reason']}")
                dest(f"  {EMOJI["text"]    } {ident['message']}")
                dest()
        elif ident['valid'] is None:  # valid is None, because we haven't checked for validity
            dest(f"{md_check_list}{size}{type_indicator} {ident['full_link']}")
            if not clean:
                dest(f"  {EMOJI["file"]    } {ident['file']}")
                dest()

    #dest(f"\n{EMOJI['invite']} Printed {len(identifiers_list)} identifier" + ('s' if len(identifiers_list) > 1 else ''))

def print_identifiers_binned(identifiers_list, md_tasks=False, active_only=False, clean=False, tg_list=False):
    """Print identifiers grouped by member count bins, with users at the end."""
    if not identifiers_list:
        return

    # Separate users from channels/groups
    users = [i for i in identifiers_list if i.get('entity_type') in ('user', 'bot')]
    non_users = [i for i in identifiers_list if i.get('entity_type') not in ('user', 'bot')]

    # Group non-users into bins
    binned = {label: [] for label, _, _ in SIZE_BINS}
    unknown_bin = []

    for ident in non_users:
        label = get_size_bin_label(ident.get('member_count'))
        if label is None:
            unknown_bin.append(ident)
        else:
            binned[label].append(ident)

    # Print each bin in order
    for label, _, _ in SIZE_BINS:
        entries = sorted(binned[label], key=lambda i: i['member_count'], reverse=True)
        if not entries:
            continue
        LOG.output()
        LOG.output(f"{EMOJI['folder']} in {label} • {len(entries)} identifier{'s' if len(entries) > 1 else ''}")
        LOG.output(UI_HORIZONTAL_LINE)
        print_identifiers(entries, md_tasks, active_only, clean, tg_list, show_size=True)
        LOG.output(UI_HORIZONTAL_LINE)

    # Unknown bin (no member count available)
    if unknown_bin:
        LOG.output()
        LOG.output(f"{EMOJI['unknown']} With unknown count • {len(unknown_bin)} identifier{'s' if len(unknown_bin) > 1 else ''}")
        LOG.output(UI_HORIZONTAL_LINE)
        print_identifiers(unknown_bin, md_tasks, active_only, clean=False, tg_list=tg_list)
        LOG.output(UI_HORIZONTAL_LINE)

    # Users at the end
    if users:
        LOG.output()
        LOG.output(f"{EMOJI['handle']} Users • {len(users)} identifier{'s' if len(users) > 1 else ''}")
        LOG.output(UI_HORIZONTAL_LINE)
        print_identifiers(users, md_tasks, active_only, clean, tg_list)
        LOG.output(UI_HORIZONTAL_LINE)


def list_identifiers(client, md_files, args):
    identifiers_list = []
    for md_file in md_files:
        try:
            entity = TelegramEntity.from_file(md_file)

            # Skip files with type = 'user' or 'bot'
            entity_type = None
            try:
                entity_type = entity.get_type()
            except MissingFieldError:
                pass
            except InvalidTypeError:
                continue
            if not args.include_users and entity_type in ('user', 'bot'):
                continue

            # Skip files with banned/unknown status unless --no-skip
            if not args.no_skip:
                last_status, _, _ = get_last_status(entity)
                if last_status in ['banned', 'unknown', 'deleted']:
                    continue

            # Skip files if type is defined
            if args.type and entity_type not in args.type:
                continue

            # Get size for binning
            size = None
            if args.sort_size:
                size = entity.get_size()

            # Get invites
            invites = entity.get_invites().active()

            for invite in invites:
                invite_entry = {
                    'file': md_file.name,
                    'short': invite.hash,
                    'full_link': f'https://t.me/+{invite.hash}',
                    'entity_type': entity_type,
                    'member_count': size,
                }

                # Validate if in 'valid' mode
                if args.get_identifiers == 'valid':
                    (
                        invite_entry['valid'],
                        invite_entry['user_id'],
                        invite_entry['reason'],
                        invite_entry['message']
                    ) = validate_invite(client, invite.hash)
                    sleep(SLEEP_BETWEEN_CHECKS)  # Rate limiting
                else:
                    # 'all' mode - no validation
                    invite_entry['valid'] = None
                    invite_entry['reason'] = None
                    invite_entry['message'] = "Not validated"

                if args.continuous:
                    print_identifiers([invite_entry], args.md_tasks, args.active_only, args.clean, args.tg_list)
                else:
                    identifiers_list.append(invite_entry)
                    print_identifiers([invite_entry], args.md_tasks, args.active_only, args.clean, args.tg_list, dest=LOG.info)

            # Add usernames if not --invites-only
            if not args.invites_only:
                usernames = entity.get_usernames().active()
                for username in usernames:
                    username_entry = {
                        'file': md_file.name,
                        'short': '@' + username.value,
                        'full_link': f'https://t.me/{username.value}',
                        'entity_type': entity_type,
                        'member_count': size,
                    }

                    # Validate if in 'valid' mode
                    if args.get_identifiers == 'valid':
                        (
                            username_entry['valid'],
                            username_entry['user_id'],
                            username_entry['reason'],
                            username_entry['message']
                        ) = validate_handle(client, username.value)
                        sleep(SLEEP_BETWEEN_CHECKS)
                    else:
                        username_entry['valid'] = None
                        username_entry['reason'] = None
                        username_entry['message'] = "Not validated"

                    if args.continuous:
                        print_identifiers([username_entry], args.md_tasks, args.active_only, args.clean, args.tg_list)
                    else:
                        identifiers_list.append(username_entry)
                        print_identifiers([username_entry], args.md_tasks, args.active_only, args.clean, args.tg_list, dest=LOG.info)

        except Exception as e:
            print_debug(e, currentframe().f_code.co_name)
            continue

    # Print results and cleanup
    if not args.continuous:
        if args.sort_size:
            print_identifiers_binned(identifiers_list, args.md_tasks, args.active_only, args.clean, args.tg_list)
        else:
            print_identifiers(identifiers_list, args.md_tasks, args.active_only, args.clean, args.tg_list)
