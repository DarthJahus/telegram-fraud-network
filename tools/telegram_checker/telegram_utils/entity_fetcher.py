from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from inspect import currentframe
from time import sleep
from telegram_checker.config.constants import EMOJI, MDML_BOOL_TRUE_SET, MDML_BOOL_FALSE_SET
from telethon.errors import (
    InviteHashExpiredError,
    InviteHashInvalidError,
    ChatAdminRequiredError
)
from telethon.tl.functions.channels import GetFullChannelRequest, GetParticipantsRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import (
    Channel, User, Chat, PeerChannel, PeerUser, PeerChat,
    ChannelParticipantsAdmins, ChannelParticipantCreator, ChannelParticipantAdmin
)
from telegram_checker.mdml_utils.mdml_parser import get_last_status, extract_telegram_identifiers
from telegram_checker.utils.exceptions import DebugException
from telegram_checker.utils.helpers import print_debug, seconds_to_time
from telegram_checker.utils.logger import get_logger
from telegram_mdml.telegram_mdml import (
    TelegramMDMLError,
    TelegramEntity,
    InvalidTypeError,
    MissingFieldError,
    InvalidFieldError
)

LOG = get_logger()


class SkipReasonType(Enum):
    STATUS          = 'status'
    STATUS_TIME     = 'check time'
    FIELD_TIME      = 'field time'
    FIELD_EXISTS    = 'field exists'
    FIELD_VALUE     = 'field has value'
    FIELD_VALUE_INV = 'field does not have value'
    NO_SKIP         = 'no_skip_unknown'


@dataclass
class SkipReason:
    type: SkipReasonType
    message: str

    def __bool__(self):
        return True

    def __str__(self):
        return self.message


def fetch_entity_info(client, identifier: str):
    """
    Fetches comprehensive information about a Telegram entity.

    Args:
        client: TelegramClient instance
        identifier: invite, invite hash, id or [@]username
    Returns:
        dict: Entity information or None on error
    """

    # Determine which method to use
    entity = None
    invite_link = None
    try:
        if identifier.isdecimal():
            # By ID
            LOG.info(f"Fetching entity by ID: {identifier}...", EMOJI['id'])
            identifier = int(identifier)
            try:
                # Try different peer types
                try:
                    entity = client.get_entity(PeerChannel(identifier))
                except Exception as e:
                    print_debug(DebugException('From client.get_entity(PeerChannel(identifier))'))
                    print_debug(e, currentframe().f_code.co_name)
                    try:
                        entity = client.get_entity(PeerUser(identifier))
                    except Exception as e:
                        print_debug(DebugException('From client.get_entity(PeerUser(identifier))'))
                        print_debug(e, currentframe().f_code.co_name)
                        try:
                            entity = client.get_entity(PeerChat(identifier))
                        except Exception as e:
                            print_debug(DebugException('From client.get_entity(PeerChat(identifier))'))
                            print_debug(e, currentframe().f_code.co_name)
                            entity = client.get_entity(identifier)
            except ValueError:
                # ID not in session cache - need to encounter it first
                LOG.error(f"Cannot resolve ID {identifier}: not found in session cache", EMOJI['error'])
                LOG.info("This ID hasn't been encountered yet in this session.", EMOJI['info'])
                LOG.info("Try using --by-username or --by-invite to resolve the entity first.", EMOJI['info'])
                return None

        elif '+' in identifier:
            # By invite
            LOG.info(f"Fetching entity by invite: {identifier}...", EMOJI['invite'])

            # Get hash without + or extract hash from URL
            invite_hash = identifier.split('+')[-1] if '+' in identifier else identifier.split('/')[-1]
            invite_link = f'https://t.me/+{invite_hash}'

            # Try to get entity first
            try:
                entity = client.get_entity(f'https://t.me/+{invite_hash}')
                print_debug(DebugException("got entity = client.get_entity"), currentframe().f_code.co_name)
            except ValueError as e:
                if "Cannot get entity from a channel" in str(e):
                    # Not a member - use CheckChatInviteRequest for preview
                    LOG.info("Not a member. Trying invite preview...", EMOJI['info'])

                    try:
                        from telethon.tl.functions.messages import CheckChatInviteRequest
                        from telethon.tl.types import ChatInvite, ChatInvitePeek, ChatInviteAlready

                        result = client(CheckChatInviteRequest(hash=invite_hash))
                        print_debug(DebugException("got result = client(CheckChatInviteRequest())"), currentframe().f_code.co_name)

                        # Already a member (shouldn't happen after ValueError, but safety check)
                        if isinstance(result, ChatInviteAlready):
                            entity = result.chat

                        # Preview available
                        elif isinstance(result, (ChatInvite, ChatInvitePeek)):
                            info = {
                                'type': 'channel' if result.broadcast else 'group',
                                'id': None,
                                'name': result.title,
                                'count': result.participants_count if hasattr(result, 'participants_count') else None,
                                'invite_link': invite_link,
                                'is_preview': True
                            }
                            # Add photo/bio if available in preview
                            if hasattr(result, 'about') and result.about:
                                info['bio'] = result.about

                            return info

                    except InviteHashExpiredError:
                        LOG.error("Invite link has expired", EMOJI['error'])
                        return None

                    except InviteHashInvalidError:
                        LOG.error("Invite link is invalid", EMOJI['error'])
                        return None

                    except Exception as e:
                        LOG.error(f"Failed to get invite preview: {type(e).__name__}", EMOJI['error'])
                        print_debug(e, currentframe().f_code.co_name)
                        return None
                else:
                    # Other ValueError
                    LOG.error(f"Error with invite: {str(e)}", EMOJI['error'])
                    print_debug(e, currentframe().f_code.co_name)
                    return None

        else:
            # By username
            if not identifier.startswith('@'): identifier = '@' + identifier
            LOG.info(f"Fetching entity by username: {identifier}...", EMOJI['handle'])
            entity = client.get_entity(identifier)

        if not entity:
            LOG.error(f"{EMOJI['error']} Could not retrieve entity")
            return None

        LOG.info(f"Entity retrieved!", EMOJI['success'])

        # Get full entity information
        full = None
        if isinstance(entity, Channel):
            full = client(GetFullChannelRequest(entity))
        elif isinstance(entity, User):
            full = client(GetFullUserRequest(entity))

        # Determine entity type
        entity_type = None
        if isinstance(entity, User):
            entity_type = 'bot' if entity.bot else 'user'
        elif isinstance(entity, Channel):
            if entity.megagroup:
                entity_type = 'group'
            elif entity.broadcast:
                entity_type = 'channel'
            else:
                entity_type = 'group'
        elif isinstance(entity, Chat):
            entity_type = 'group'

        # Build info dict
        info = {
            'entity': entity,
            'full': full,
            'type': entity_type,
            'id': entity.id,
            'invite_link': invite_link
        }

        # Join date (only for channels/groups where we are members)
        if isinstance(entity, (Channel, Chat)):
            # Check if we are actually a member
            is_member = False
            if isinstance(entity, Channel):
                # For channels, check if we have access (not just preview)
                is_member = not entity.left  # Si left=False, on est membre
            elif isinstance(entity, Chat):
                is_member = True  # For Chats, if we have access, then we are members
            if is_member and hasattr(entity, 'date') and entity.date:
                info['joined_date'] = entity.date.astimezone().strftime('%Y-%m-%d %H:%M')

        # Username
        if hasattr(entity, 'username') and entity.username:
            info['usernames'] = [(entity.username, True)]
        elif hasattr(entity, 'usernames') and entity.usernames:
            # for groups that might have more than one username (Fragment)
            info['usernames'] = [(un.username, un.active) for un in entity.usernames]

        # Name
        if isinstance(entity, User):
            parts = []
            if entity.first_name:
                parts.append(entity.first_name)
            if entity.last_name:
                parts.append(entity.last_name)
            info['name'] = ' '.join(parts) if parts else None
        elif isinstance(entity, (Channel, Chat)):
            info['name'] = entity.title

        if full:
            # Bio
            bio_text = None
            if hasattr(full, 'full_chat') and hasattr(full.full_chat, 'about'):
                bio_text = full.full_chat.about
            elif hasattr(full, 'full_user') and hasattr(full.full_user, 'about'):
                bio_text = full.full_user.about

            # Only add bio if it exists and is not empty/whitespace
            if bio_text and bio_text.strip():
                info['bio'] = bio_text.strip()

            # Linked chats and personal chat
            if hasattr(full, 'chats'):
                info['linked_chats'] = full.chats
            if hasattr(full, 'full_user') and hasattr(full.full_user, 'personal_channel_id'):
                info['personal_chat_id'] = full.full_user.personal_channel_id

        # Mobile (phone)
        if isinstance(entity, User) and hasattr(entity, 'phone') and entity.phone:
            info['mobile'] = entity.phone if entity.phone.startswith('+') else f"+{entity.phone}"

        # Created date and first message
        if isinstance(entity, Channel):
            try:
                from telethon.tl.types import MessageService, MessageActionChannelMigrateFrom
                messages = client.get_messages(entity, limit=1, reverse=True)
                if hasattr(messages, 'total') and messages.total > 0 and len(messages) == 0:
                    # Messages exist, but access is restrained
                    LOG.debug(f"Channel has {messages.total} messages but history is restricted")
                elif len(messages) > 0:
                    first_msg = messages[0]
                    info['created_date'] = first_msg.date.astimezone().strftime('%Y-%m-%d')
                    info['created_msg_id'] = first_msg.id
                    # Detect migration
                    if isinstance(first_msg, MessageService) and isinstance(first_msg.action, MessageActionChannelMigrateFrom):
                        info['is_migrated'] = True
                        info['original_chat_id'] = first_msg.action.chat_id
            except Exception as e:
                print_debug(e, currentframe().f_code.co_name)
                pass

        # Linked channel/discussion
        if isinstance(entity, Channel) and full:
            if hasattr(full, 'full_chat') and hasattr(full.full_chat, 'linked_chat_id'):
                if full.full_chat.linked_chat_id:
                    username = None
                    if hasattr(full.full_chat, 'username') and full.full_chat.username:
                        username = full.full_chat.username
                    elif hasattr(full.full_chat, 'usernames') and full.full_chat.usernames:
                        for un in full.full_chat.usernames:
                            if un.active:
                                username = un.username
                                break
                    info['linked_chat'] = (full.full_chat.linked_chat_id, username)

        # Members/Subscribers count
        if full:
            if hasattr(full, 'full_chat') and hasattr(full.full_chat, 'participants_count'):
                info['count'] = full.full_chat.participants_count

        # Owner and admins
        try:
            if isinstance(entity, Channel):
                admins_result = client(GetParticipantsRequest(
                    channel=entity,
                    filter=ChannelParticipantsAdmins(),
                    offset=0,
                    limit=100,
                    hash=0
                ))

                if admins_result.participants:
                    owner = None
                    admins = []
                    users_map = {user.id: user for user in admins_result.users}
                    for participant in admins_result.participants:
                        user = users_map.get(participant.user_id)
                        name = ' '.join(filter(None, [user.first_name, user.last_name])) if user else None
                        username = None
                        if user and user.username:
                            username = user.username
                        elif user and user.usernames:
                            for un in user.usernames:
                                if un.active:
                                    username = un.username
                                    break
                        if isinstance(participant, ChannelParticipantCreator):
                            owner = (
                                participant.user_id,
                                username,
                                name
                            )
                        elif isinstance(participant, ChannelParticipantAdmin):
                            admins.append((
                                participant.user_id,
                                username,
                                name
                            ))
                        else:
                            # Shouldn't happen, since it's filtered
                            print_debug(DebugException(f"Participant type unexpected: {type(participant)}"), 'fetch_entity_info():owner_and_admins:shouldnt_happen')

                    if owner:
                        info['owner'] = owner
                    if admins:
                        info['admins'] = admins
        except ChatAdminRequiredError:
            LOG.debug("Cannot get admins and owner. You do not have permissions to access this information.")
        except Exception as e:
            print_debug(e, currentframe().f_code.co_name)
            pass

        return info

    except ValueError as e:
        LOG.error(f"Invalid ID.", EMOJI['error'])
        print_debug(e, currentframe().f_code.co_name)
        return None
    except Exception as e:
        LOG.output(f"Error retrieving entity: {e}", EMOJI['error'])
        print_debug(e, currentframe().f_code.co_name)
        return None


def should_skip_entity(entity, skip_statuses, no_skip_unknown=False, skip_by_check=True, skip_time_seconds=None, skip_fields:list[dict[str, (str or SkipReasonType or any)]]=None) -> (bool, SkipReason or None):
    """
    Determines if an entity should be skipped based on its last status.

    :param entity: (TelegramEntity): Telegram MDML entity
    :param skip_statuses: (list or None): Skip if last status is in this list
    :param no_skip_unknown: (default: False): Don't skip when last_stats is Unknown
    :param skip_by_check:
    :param skip_time_seconds:
    :param skip_fields: additional fields for skip reasons
        - field_name: str
        - skip_reason: SkipReasonType
        - check_value: value to check against

    Returns:
        tuple: (should_skip, reason: SkipReason or None) where reason explains why it was skipped
    """

    last_state, last_datetime, has_state_block = get_last_status(entity)

    if last_state is None:
        # No previous status, don't skip
        return False, None

    # Check if we should skip based on status
    if skip_statuses and last_state in skip_statuses:
        return True, SkipReason(SkipReasonType.STATUS, f"last status '{last_state}' in {skip_statuses!r}")

    # Exceptions with unknown
    if last_state == "unknown" and no_skip_unknown:
        # explicitly don't skip unknown (by user)
        return False, SkipReason(SkipReasonType.NO_SKIP, f"last status is 'unknown', but --no-skip-unknown is used")

    # last check is time
    if skip_by_check and skip_time_seconds and last_datetime:
        time_since_check = datetime.now() - last_datetime
        if time_since_check.total_seconds() < skip_time_seconds:
            return True, SkipReason(SkipReasonType.STATUS_TIME, f"checked {seconds_to_time(time_since_check.total_seconds())} ago (status: {last_state})")

    if skip_fields:
        for skip_field in skip_fields:
            fv = entity.get_field_last(skip_field['field_name'])

            if skip_field['skip_reason'] is SkipReasonType.FIELD_EXISTS and fv:
                return True, SkipReason(SkipReasonType.FIELD_EXISTS, f"{skip_field['field_name']} found in entity")

            if skip_field["skip_reason"] is SkipReasonType.FIELD_TIME and isinstance(skip_field['check_value'], int):
                if fv and fv.date:
                    age = (datetime.now() - fv.date).total_seconds()
                    if age < skip_field['check_value']:
                        return True, SkipReason(SkipReasonType.FIELD_TIME, f"{skip_field['field_name']} {seconds_to_time(age)} ago")

            if fv and skip_field["skip_reason"] in (SkipReasonType.FIELD_VALUE, SkipReasonType.FIELD_VALUE_INV):
                fv_value_l = str(fv.value).lower().strip()
                check = skip_field['check_value']
                match = None
                if isinstance(check, bool):
                    match = fv_value_l in (MDML_BOOL_TRUE_SET if check is True else MDML_BOOL_FALSE_SET)
                elif isinstance(check, list):
                    check_set = {str(v).lower().strip() for v in check}
                    match = fv_value_l in check_set
                elif isinstance(check, str):
                    match = fv_value_l == check.lower().strip()
                if match is not None:
                    if skip_field["skip_reason"] == SkipReasonType.FIELD_VALUE_INV:
                        match = not match
                    if match:
                        return True, SkipReason(skip_field["skip_reason"], f"{skip_field['field_name']} matched condition: {skip_field["skip_reason"].value} {check!r} (actual: {fv_value_l})")

    return False, None


def iter_md_entities(args, md_files, stats, skip_time_seconds=None, skip_fields:list[dict[str, (str or SkipReasonType or any)]]=None, progress_bar=None):
    """
    Parse, filter, and skip-check each MD file.
    Yields a dict with everything pre-extracted for full_check / mass_report.
    Increments stats['skipped'] and sub-keys on skip.
    """
    for md_file in md_files:
        if progress_bar:
            progress_bar['bar'].update(progress_bar['task'], entity=md_file.stem)
            progress_bar['bar'].advance(progress_bar['task'])
        try:
            entity = TelegramEntity.from_file(md_file)
            LOG.info()
            LOG.info(f"\\[[{md_file.name}\\]]", EMOJI["file"])

            # Type filter
            try:
                entity_type = entity.get_type()
            except (InvalidTypeError, MissingFieldError):
                entity_type = None
            except Exception as e:
                LOG.error(f"{EMOJI['error']} Error: {e}")
                entity_type = None

            if args.type and entity_type not in args.type:
                stats['skipped'] += 1
                stats['skipped_type'] += 1
                LOG.info(
                    f"Skipped: entity type {entity_type} not {', neither '.join(args.type)}",
                    emoji=EMOJI['skip'],
                    padding=2
                )
                continue

            # Identifiers
            try:
                expected_id = entity.get_id()
            except InvalidFieldError:
                expected_id = None
            except Exception as e:
                LOG.error(f"{EMOJI['error']} Error: {e}")
                expected_id = None

            identifiers, is_invite = extract_telegram_identifiers(entity)

            if not expected_id and not identifiers:
                LOG.info(f"  {EMOJI['skip']} Skipped: No identifier found")
                stats['skipped'] += 1
                stats['skipped_no_identifier'] += 1
                continue

            # Skip logic
            should_skip, skip_reason = should_skip_entity(
                entity,
                args.skip,
                args.no_skip_unknown,
                skip_time_seconds=skip_time_seconds,
                skip_by_check=(skip_fields is None),
                skip_fields=skip_fields
            )
            if should_skip:
                LOG.info(f"Skipped: {skip_reason}", padding=2, emoji=EMOJI['skip'])
                stats['skipped'] += 1
                if isinstance(skip_reason, SkipReason):
                    if skip_reason.type == SkipReasonType.STATUS_TIME:
                        stats['skipped_time'] += 1
                    elif skip_reason.type == SkipReasonType.STATUS:
                        stats['skipped_status'] += 1
                    elif skip_reason.type in (SkipReasonType.FIELD_TIME, SkipReasonType.FIELD_EXISTS, SkipReasonType.FIELD_VALUE):
                        stats['skipped_field'] += 1
                continue
            elif skip_reason:
                LOG.info(f"Not skipping: {skip_reason}", padding=2, emoji=EMOJI['info'])

            last_status, last_datetime, has_status_block = get_last_status(entity)

            yield {
                'md_file':          md_file,
                'entity':           entity,
                'expected_id':      expected_id,
                'identifiers':      ['+' + ident for ident in identifiers] if is_invite else identifiers,
                'is_invite':        is_invite,
                'last_status':      last_status,
                'last_datetime':    last_datetime,
                'has_status_block': has_status_block,
            }

        except FileNotFoundError:
            stats['skipped'] += 1
            stats['skipped_error'] = stats.get('skipped_error', 0) + 1
            LOG.error("File not found.", EMOJI['error'])
        except TelegramMDMLError:
            stats['skipped'] += 1
            stats['skipped_error'] = stats.get('skipped_error', 0) + 1
            LOG.error("Parsing failed.", EMOJI['error'])
        except Exception as e:
            stats['skipped'] += 1
            stats['skipped_error'] = stats.get('skipped_error', 0) + 1
            LOG.error("Failed to read MDML entity from file.", EMOJI['error'])
            print_debug(e, currentframe().f_code.co_name)
        except KeyboardInterrupt:
            LOG.info('CTRL+C detected. Entity skipped by user. Press CTRL+C again to quit.', emoji=EMOJI['skip'])
            try:
                sleep(2)
            except KeyboardInterrupt:
                raise
            continue
