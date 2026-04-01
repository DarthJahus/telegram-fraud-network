from inspect import currentframe
from time import sleep
from telegram_checker.telegram_utils.entity_actions import join_entity, add_contact
from telegram_checker.telegram_utils.exceptions import TelegramUtilsActionAddContactError, TelegramUtilsActionJoinEntityError
from telegram_checker.utils.exceptions import DebugException
from telegram_checker.utils.logger import get_logger, create_progress_bar
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


def print_identifiers(identifiers_list, md_tasks=False, active_only=False, clean=False, tg_list=False, show_size=False, numbered=True, dest=LOG.output):
    if not identifiers_list:
        return

    n = 0

    bin_length_digits = 0
    if numbered:
        valid_count = sum(1 for i in identifiers_list if i['valid'] is True)
        bin_length_digits = len(str(valid_count))

    max_member_count_digits = 0
    if show_size:
        sizes = [i['member_count'] for i in identifiers_list if i['member_count'] is not None]
        max_member_count_digits = len(str(max(sizes))) if sizes else 0

    def build_prefix(n_val, size_val):
        parts = []
        if show_size:
            parts.append(f"{size_val:>{max_member_count_digits}}" if size_val is not None else ' ' * max_member_count_digits)
        if numbered:
            parts.append(f"{n_val:>{bin_length_digits}}")

        block = " | ".join(parts) + " |" if parts else ""

        if md_tasks:
            return f"- [ ] {block} " if block else "- [ ] "
        elif tg_list:
            return f"`{block}` " if block else ""
        else:
            return f"{block} " if block else ""

    for ident in identifiers_list:
        type_indicator = EMOJI['invite'] if "+" in ident['full_link'] else EMOJI['handle']

        if ident['valid'] is True:
            n += 1
            prefix = build_prefix(n_val=n, size_val=ident['member_count'])
            state = f"{EMOJI['active']} " if not active_only else ""
            dest(f"{prefix}{state}{type_indicator} {ident['full_link']}")
            if not clean:
                if ident['user_id']:
                    dest(f"  {EMOJI['id']      } {ident['user_id']}")
                dest(f"  {EMOJI['file']    } \\[[{ident['file']}\\]]")

        elif ident['valid'] is False and not active_only:
            prefix = build_prefix(n_val=0, size_val=ident['member_count'])
            dest(f"{prefix}{EMOJI['no_emoji']} {type_indicator} {ident['full_link']}")
            if not clean:
                dest(f"  {EMOJI['file']    } \\[[{ident['file']}\\]]")
                dest(f"  {EMOJI['text']    } \\[[{ident['reason']}\\]]")
                dest(f"  {EMOJI['text']    } \\[[{ident['message']}\\]]")

        elif ident['valid'] is None and not active_only:
            prefix = build_prefix(n_val=0, size_val=ident['member_count'])
            dest(f"{prefix}{type_indicator} {ident['full_link']}")
            if not clean:
                dest(f"  {EMOJI['file']    } \\[[{ident['file']}\\]]")


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

    progress_bar = create_progress_bar(LOG, md_files, 'Listing...')
    progress_bar['bar'].start()

    for md_file in md_files:
        progress_bar['bar'].update(progress_bar['task'], entity=md_file.stem)
        progress_bar['bar'].advance(progress_bar['task'])

        invite_entry = None
        username_entry = None
        LOG.debug(f'Handling file {md_file.name}...')
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
                LOG.info(f'Skipping entity with type {entity_type} not {', neither '.join(args.type)}', emoji=EMOJI['skip'])
                continue

            # Get size for binning
            size = None
            if args.sort_size:
                try:
                    size = entity.get_size()
                except ValueError as e:
                    print_debug(DebugException(e))

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
                    LOG.debug(f"Sleeping 2×{SLEEP_BETWEEN_CHECKS} seconds...", padding=2)
                    sleep(2*SLEEP_BETWEEN_CHECKS)  # Rate limiting
                else:
                    # 'all' mode - no validation
                    invite_entry['valid'] = None
                    invite_entry['reason'] = None
                    invite_entry['message'] = "Not validated"

                if args.continuous:
                    print_identifiers([invite_entry], args.md, args.active_only, args.clean, args.tg_list, numbered=False)
                else:
                    identifiers_list.append(invite_entry)
                    print_identifiers([invite_entry], args.md, args.active_only, args.clean, args.tg_list, dest=LOG.info, numbered=False)

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
                        LOG.debug(f"Sleeping {SLEEP_BETWEEN_CHECKS} seconds...", padding=2)
                        sleep(SLEEP_BETWEEN_CHECKS)
                    else:
                        username_entry['valid'] = None
                        username_entry['reason'] = None
                        username_entry['message'] = "Not validated"

                    if args.continuous:
                        print_identifiers([username_entry], args.md, args.active_only, args.clean, args.tg_list, numbered=False)
                    else:
                        identifiers_list.append(username_entry)
                        print_identifiers([username_entry], args.md, args.active_only, args.clean, args.tg_list, dest=LOG.info, numbered=False)

            # Try to join if --join
            if args.join and ((username_entry and username_entry['valid']) or (invite_entry and invite_entry['valid'])):
                LOG.info("Trying to join entity...", emoji=EMOJI['change'], padding=2)
                LOG.debug(f"Sleeping {SLEEP_BETWEEN_CHECKS} seconds...", padding=2)
                sleep(SLEEP_BETWEEN_CHECKS)
                try:
                    result = None
                    # Try username first (less timeout)
                    if username_entry and username_entry['valid']:
                        if username_entry['entity_type'] in ["group", "channel"]:
                            result = join_entity(client, username_entry['short'])
                        elif username_entry['entity_type'] in ["user"]:
                            result = add_contact(client, username_entry['short'])
                        elif username_entry['entity_type'] in ["bot"]:
                            LOG.info("Not adding a bot as a contact! Try interacting with /start", emoji=EMOJI['bot'], padding=4)
                        else:
                            print_debug(DebugException(f"Entity type {username_entry['entity_type']} not valid."), currentframe().f_code.co_name)
                    elif invite_entry and invite_entry['valid']:
                        result = join_entity(client, invite_entry['full_link'])

                    if result:
                        LOG.info(result.value[0], emoji=result.value[1], padding=4)

                except (TelegramUtilsActionJoinEntityError, TelegramUtilsActionAddContactError):
                    LOG.info("Action failed, skipping", emoji=EMOJI['error'], padding=4)

            LOG.info()

        except Exception as e:
            print_debug(e, currentframe().f_code.co_name)
            continue

    progress_bar['bar'].stop()

    # Print results and cleanup
    if not args.continuous:
        LOG.output(UI_HORIZONTAL_LINE)
        LOG.throttle = False
        if args.sort_size:
            print_identifiers_binned(identifiers_list, args.md, args.active_only, args.clean, args.tg_list)
        else:
            print_identifiers(identifiers_list, args.md, args.active_only, args.clean, args.tg_list)
