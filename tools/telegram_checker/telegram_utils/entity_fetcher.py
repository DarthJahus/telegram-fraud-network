from inspect import currentframe
from telegram_checker.config.constants import EMOJI
from telethon.errors import (
    InviteHashExpiredError,
    InviteHashInvalidError,
    ChatAdminRequiredError
)
from telethon.tl.functions.channels import GetFullChannelRequest, GetParticipantsRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import (
    Channel, User, Chat, PeerChannel, PeerUser, PeerChat,
    ChannelParticipantsAdmins, ChannelParticipantCreator
)
from telegram_checker.utils.helpers import print_debug
from telegram_checker.utils.logger import get_logger, DebugException

LOG = get_logger()


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
    by_invite, by_id, by_username = False, False, False

    entity = None
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
            invite_link = identifier if '+' in identifier else f'https://t.me/+{identifier}'

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
                                'by_invite': invite_link,
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
            'by_invite': by_invite
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
            info['username'] = entity.username
        elif hasattr(entity, 'usernames') and entity.usernames:
            # for groups that might have more than one username (Fragment)
            for un in entity.usernames:
                # ToDo: make it a list?
                if un.active:
                    info['username'] = un.username
                    continue

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

        # Bio
        if full:
            bio_text = None
            if hasattr(full, 'full_chat') and hasattr(full.full_chat, 'about'):
                bio_text = full.full_chat.about
            elif hasattr(full, 'full_user') and hasattr(full.full_user, 'about'):
                bio_text = full.full_user.about

            # Only add bio if it exists and is not empty/whitespace
            if bio_text and bio_text.strip():
                info['bio'] = bio_text.strip()

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
                    info['linked_chat_id'] = full.full_chat.linked_chat_id

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

                    for participant in admins_result.participants:
                        if isinstance(participant, ChannelParticipantCreator):
                            owner = participant.user_id
                        else:
                            if hasattr(participant, 'user_id'):
                                admins.append(participant.user_id)

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
