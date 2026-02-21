from inspect import currentframe
from time import sleep
from telethon.tl.functions.messages import CheckChatInviteRequest
from telethon.tl.types import ChatInviteAlready, ChatInvite, ChatInvitePeek
from telethon.errors import (
    ChannelPrivateError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    FloodWaitError
)
from telegram_checker.config.constants import EMOJI
from telegram_checker.utils.helpers import print_debug
from telegram_checker.utils.logger import get_logger, DebugException

LOG = get_logger()


def validate_invite(client, invite_hash):
    """
    Validates an invitation link by checking the invite info.
    Uses CheckChatInviteRequest to validate the invite,
    then attempts to retrieve the entity ID via get_entity.

    Args:
        client: TelegramClient instance
        invite_hash: Invite hash to validate

    Returns:
        tuple: (is_valid, user_id or None, reason or None, message or None)
    """
    try:
        # Check the invite (returns ChatInviteAlready, ChatInvite, or ChatInvitePeek)
        result = client(CheckChatInviteRequest(hash=invite_hash))

        # Invitation is valid - now try to get the entity ID
        entity_id = None
        message = None
        try:
            entity = client.get_entity(f'https://t.me/+{invite_hash}')
            if hasattr(entity, 'id'):
                entity_id = entity.id
            else:
                # Should never happen
                print_debug(DebugException("SHOULD NEVER HAVE HAPPENED"))
        except ValueError as e:
            message = str(e)
        except Exception as e:
            print_debug(e, currentframe().f_code.co_name)
            # Can't get entity, but invite is still valid
            pass

        # Determine reason based on result type
        if isinstance(result, ChatInviteAlready):
            reason = 'ALREADY_MEMBER'
        elif isinstance(result, ChatInvite):
            reason = 'VALID_PREVIEW'
        elif isinstance(result, ChatInvitePeek):
            reason = 'VALID_PEEK'
        else:
            reason = 'VALID_UNKNOWN_TYPE'

        return True, entity_id, reason, message

    except InviteHashExpiredError as e:
        return False, None, 'EXPIRED', str(e)
    except InviteHashInvalidError as e:
        return False, None, 'INVALID', str(e)

    except FloodWaitError as e:
        # Handle flood wait with recursive retry
        LOG.error(f"{EMOJI['pause']} FloodWait: waiting {e.seconds}s...")
        sleep(e.seconds)
        return validate_invite(client, invite_hash)

    except Exception as e:
        print_debug(e, currentframe().f_code.co_name)
        return False, None, 'ERROR', f'{type(e).__name__}: {str(e)}'


def validate_handle(client, username):
    """
    Validates if a Telegram handle (@username) is valid and leads somewhere.

    Args:
        client: TelegramClient instance
        username: Username without @ (e.g., 'example_channel')

    Returns:
        tuple: (is_valid, reason, message)
            - is_valid: True if handle is accessible
            - reason: 'valid', 'invalid', 'not_occupied', 'private', or 'error'
            - message: Descriptive message or None
    """
    try:
        entity = client.get_entity(username)
        # If we get here, the handle is valid and accessible
        return True, entity.id, 'valid', None
    except ValueError as e:
        return False, None, 'NO_USER', str(e)
    except UsernameNotOccupiedError:
        return False, None, 'not_occupied', 'Username not occupied'
    except UsernameInvalidError:
        return False, None, 'invalid', 'Invalid username format'
    except ChannelPrivateError:
        # Handle exists but is private/requires membership
        return True, None, 'private', 'Channel/group is private'
    except FloodWaitError as e:
        # Handle flood wait with recursive retry
        LOG.error(f"  {EMOJI['pause']} FloodWait: waiting {e.seconds}s...")
        sleep(e.seconds)
        return validate_handle(client, username)
    except Exception as e:
        print_debug(e, currentframe().f_code.co_name)
        return False, None, 'ERROR', f'{type(e).__name__}: {str(e)}'
