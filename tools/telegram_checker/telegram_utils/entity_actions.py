from telegram_checker.telegram_utils.constants import JoinResults
from telegram_checker.telegram_utils.exceptions import (
    TelegramUtilsClientError,
    TelegramUtilsActionAddContactError,
    TelegramUtilsActionJoinEntityError
)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
from telethon.tl.functions.contacts import AddContactRequest
from telethon.errors import (
    FloodWaitError,
    UserAlreadyParticipantError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    ChannelPrivateError, InviteRequestSentError,
)
from telegram_checker.utils.helpers import sleep_with_progress
from telegram_checker.config.constants import EMOJI
from telegram_checker.utils.logger import get_logger

LOG = get_logger()


def join_entity(client=None, entity=None):
    """
    Join a group or channel.
    :param client: Telethon client
    :param entity: str — '@username', 'https://t.me/+HASH', '+HASH', or a numeric id (str/int)
    :raises TelegramUtilsJoinEntityError:
    """
    try:
        if isinstance(entity, str) and entity.startswith('@'):
            client(JoinChannelRequest(entity))
        else:
            hash_part = str(entity).split('t.me/+')[-1].lstrip('+')
            client(ImportChatInviteRequest(hash_part))
        return JoinResults.JOINED
    except InviteRequestSentError:
        return JoinResults.REQUESTED
    except UserAlreadyParticipantError:
        return JoinResults.ALREADY_MEMBER
    except (InviteHashExpiredError, InviteHashInvalidError, ChannelPrivateError) as e:
        raise TelegramUtilsActionJoinEntityError from e
    except FloodWaitError as e:
        sleep_with_progress(e.seconds, dest=LOG.error, emoji=EMOJI["pause"])
        return join_entity(client=client, entity=entity)
    except Exception as e:
        raise TelegramUtilsActionJoinEntityError from e


def add_contact(client=None, entity=None):
    """
    Add a user as a contact.
    :param client: Telethon client
    :param entity: str — '@username' or numeric id (str/int)
    :raises TelegramUtilsAddContactError:
    """
    try:
        # Try to resolve first_name, fallback to entity string
        first_name = str(entity)
        phone = ""
        try:
            resolved = client.get_entity(entity)
            parts = []
            if getattr(resolved, 'first_name', None): parts.append(resolved.first_name)
            if getattr(resolved, 'last_name', None): parts.append(resolved.last_name)
            if parts:
                first_name = ' '.join(parts)
            if getattr(resolved, 'phone', None):
                phone = resolved.phone if resolved.phone.startswith('+') else f"+{resolved.phone}"
        except Exception:
            pass
        client(AddContactRequest(
            id=entity,
            first_name=first_name,
            last_name="",
            phone=phone,
            add_phone_privacy_exception=False,
        ))
        return JoinResults.ADDED
    except FloodWaitError as e:
        sleep_with_progress(e.seconds, dest=LOG.error, emoji=EMOJI["pause"])
        return add_contact(client=client, entity=entity)
    except Exception as e:
        raise TelegramUtilsActionAddContactError from e
