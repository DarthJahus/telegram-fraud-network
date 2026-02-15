from time import sleep
from telegram_checker.utils.logger import get_logger
from telegram_checker.config.constants import EMOJI, SLEEP_BETWEEN_CHECKS
from telegram_mdml.telegram_mdml import TelegramEntity
from telegram_mdml.telegram_mdml import (
    MissingFieldError,
    InvalidTypeError
)
from telegram_checker.mdml_utils.mdml_parser import (
    get_last_status
)
from telegram_checker.telegram_utils.validators import validate_invite, validate_handle
from telegram_checker.utils.helpers import print_debug

LOG = get_logger()


def print_identifiers(identifiers_list, md_tasks=True, valid_only=False, clean=False):
    if not identifiers_list:
        return

    md_check_list = ''
    if md_tasks:
        md_check_list = '- [ ] '

    # Print results
    if len(identifiers_list) > 1:
        LOG.output(f"\n{EMOJI['invite']} Found {len(identifiers_list)} identifiers:\n")

    for ident in identifiers_list:
        type_indicator = ' ' + (EMOJI['invite'] if "+" in ident['full_link'] else EMOJI['handle'])
        if ident['valid'] is True:
            LOG.output(f"{md_check_list}{EMOJI["active"]}{type_indicator} {ident['full_link']}")
            if not clean:
                if ident['user_id']:
                    LOG.output(f"  {EMOJI["id"]      } {ident['user_id']}")
                LOG.output(f"  {EMOJI["file"]    } {ident['file']}")
                LOG.output()
        elif ident['valid'] is False and not valid_only:
            LOG.output(f"{md_check_list}{EMOJI["no_emoji"]}{type_indicator} {ident['full_link']}")
            if not clean:
                LOG.output(f"  {EMOJI["file"]    } {ident['file']}")
                LOG.output(f"  {EMOJI["text"]    } {ident['reason']}")
                LOG.output(f"  {EMOJI["text"]    } {ident['message']}")
                LOG.output()
        elif ident['valid'] is None:  # valid is None, because we haven't checked for validity
            LOG.output(f"{md_check_list}{type_indicator} {ident['full_link']}")
            if not clean:
                LOG.output(f"  {EMOJI["file"]    } {ident['file']}")
                LOG.output()


def list_identifiers(client, md_files, args):
    identifiers_list = []
    for md_file in md_files:
        try:
            entity = TelegramEntity.from_file(md_file)

            # Skip files with type = 'user' or 'bot'
            if not args.include_users:
                try:
                    if entity.get_type() in ('user', 'bot'):
                        continue
                except MissingFieldError:
                    # No type detected
                    # Process as if not user
                    pass
                except InvalidTypeError:
                    # Probably 'website' or placeholder
                    # Skip
                    continue

            # Skip files with banned/unknown status unless --no-skip
            if not args.no_skip:
                last_status, _, _ = get_last_status(entity)
                if last_status in ['banned', 'unknown', 'deleted']:
                    continue

            # Get invites
            invites = entity.get_invites().active()

            for invite in invites:
                invite_entry = {
                    'file': md_file.name,
                    'short': invite.hash,
                    'full_link': f'https://t.me/+{invite.hash}',
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
                    print_identifiers([invite_entry], args.md_tasks, args.valid_only, args.clean)
                else:
                    identifiers_list.append(invite_entry)

            # Add usernames if not --invites-only
            if not args.invites_only:
                usernames = entity.get_usernames().active()
                for username in usernames:
                    username_entry = {
                        'file': md_file.name,
                        'short': '@' + username.value,
                        'full_link': f'https://t.me/{username.value}',
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
                        print_identifiers([username_entry], args.md_tasks, args.valid_only, args.clean)
                    else:
                        identifiers_list.append(username_entry)

        except Exception as e:
            print_debug(e)
            continue

    # Print results and cleanup
    if not args.continuous:
        print_identifiers(identifiers_list, args.md_tasks, args.valid_only, args.clean)
