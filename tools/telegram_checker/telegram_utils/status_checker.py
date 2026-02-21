from time import sleep
from telegram_checker.config.constants import EMOJI
from telethon.errors import (
    ChannelPrivateError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    FloodWaitError
)
from telegram_checker.utils.helpers import print_debug
from telegram_checker.utils.logger import get_logger
LOG = get_logger()

# ============================================
# ENTITY STATUS CHECKING
# ============================================

def check_entity_by_id(client, entity_id):
    """
    Tries to get entity directly by ID (most reliable if client is member).

    Args:
        client: TelegramClient instance
        entity_id (int): Entity ID

    Returns:
        tuple: (success, entity_or_error)
    """
    try:
        from telethon.tl.types import PeerChannel, PeerUser, PeerChat

        # Try different peer types in order of likelihood
        try:
            entity = client.get_entity(PeerChannel(entity_id))
            return True, entity
        except:
            try:
                entity = client.get_entity(PeerUser(entity_id))
                return True, entity
            except:
                try:
                    entity = client.get_entity(PeerChat(entity_id))
                    return True, entity
                except:
                    # Try direct ID as last resort
                    entity = client.get_entity(entity_id)
                    return True, entity

    except ValueError as e:
        # ID not in session cache - need to encounter it first
        error_msg = f"Cannot resolve ID {entity_id}: not found in session cache. "
        error_msg += "This ID hasn't been encountered yet in this session. "
        error_msg += "Try using username or invite link to resolve the entity first."
        return False, ValueError(error_msg)

    except Exception as e:
        return False, e


def analyze_entity_status(entity):
    """
    Analyzes an entity object to determine its status.

    Args:
        entity: Telethon entity object

    Returns:
        tuple: (status, restriction_details)
    """
    # Check if user is deleted
    if hasattr(entity, 'deleted') and entity.deleted:
        return 'deleted', None

    # Check if entity is restricted (banned by Telegram)
    if hasattr(entity, 'restricted') and entity.restricted:
        if hasattr(entity, 'restriction_reason') and entity.restriction_reason:
            for restriction in entity.restriction_reason:
                if restriction.platform == 'all':
                    details = {
                        'platform': restriction.platform,
                        'reason': restriction.reason,
                        'text': restriction.text
                    }
                    return 'banned', details

            # Platform-specific restriction (not global ban)
            return 'unknown', None
        else:
            # Restricted but no reason provided
            return 'unknown', None

    return 'active', None


def check_entity_status(client, identifier=None, is_invite=False, expected_id=None):
    """
    Checks the status of a Telegram entity.

    Args:
        client: TelegramClient instance
        identifier (str, optional): Username or invite hash (None if checking by ID only)
        is_invite (bool): Whether the identifier is an invitation link
        expected_id (int, optional): Expected entity ID for verification

    Returns:
        tuple: (status, restriction_details, actual_id, method_used) where:
            - status: 'active', 'banned', 'deleted', 'id_mismatch', 'unknown', or 'error_<ExceptionName>'
            - restriction_details: dict with 'platform', 'reason', 'text' if banned, else None
            - actual_id: the actual entity ID (for id_mismatch cases), else None
            - method_used: 'id', 'username', 'invite', or 'error' (which method succeeded)

    Status meanings:
        - 'active': Successfully retrieved and entity is accessible
        - 'banned': Confirmed banned by Telegram (restricted platform='all')
        - 'deleted': Confirmed deleted account (deleted=True, users only)
        - 'id_mismatch': Username/invite exists but ID doesn't match (username reused)
        - 'unknown': Cannot determine exact status (private, changed username,
                    invalid invite, no access, platform-specific restriction, etc.)
    """

    # PRIORITY 1: Try by ID first if available
    if expected_id is not None:
        success, result = check_entity_by_id(client, expected_id)
        if success:
            entity = result
            status, restriction_details = analyze_entity_status(entity)
            retrieved_username = entity.username if hasattr(entity, 'username') else None
            return status, restriction_details, None, retrieved_username, 'id'
        # If ID fetch failed, continue to fallback methods below (if identifier provided)

        # If no identifier to fall back to, return unknown
        if identifier is None:
            return 'unknown', None, None, None, 'error'

    # If no expected_id AND no identifier, we have nothing to check
    if identifier is None:
        return 'unknown', None, None, None, 'error'

    # PRIORITY 2 & 3: Try by username or invite (fallback or primary if no ID)
    try:
        if is_invite:
            entity = client.get_entity(f'https://t.me/+{identifier}')
        else:
            entity = client.get_entity(identifier)

        # *** SAFEGUARD: Verify ID if expected_id is provided ***
        # Only check for mismatch if we actually have an expected_id
        if expected_id is not None and hasattr(entity, 'id'):
            if entity.id != expected_id:
                # This is a DIFFERENT entity with the same username/invite!
                method = 'invite' if is_invite else 'username'
                retrieved_username = entity.username if hasattr(entity, 'username') else None
                return 'id_mismatch', None, entity.id, retrieved_username, method

        # Successfully retrieved entity - now check its status
        status, restriction_details = analyze_entity_status(entity)
        method = 'invite' if is_invite else 'username'
        retrieved_id = entity.id if hasattr(entity, 'id') else None
        retrieved_username = entity.username if hasattr(entity, 'username') else None
        return status, restriction_details, retrieved_id, retrieved_username, method

    except ChannelPrivateError:
        # Channel exists, but we don't have access
        # For invites: if we can see the invite page, the channel is active
        # For usernames: the channel exists but is private
        return 'active', None, None, None, ('invite' if is_invite else 'username')

    except (InviteHashExpiredError, InviteHashInvalidError):
        # Invite is truly invalid/expired
        return 'unknown', None, None, None, 'error'

    except (UsernameInvalidError, UsernameNotOccupiedError):
        # Username doesn't exist or is invalid
        return 'unknown', None, None, None, 'error'

    except ValueError as e:
        if "Cannot get entity from a channel" in str(e):
            # This error specifically means the channel/group exists, but we're not a member
            # Different from expired/invalid invites (which raise InviteHash/Username errors)
            # Therefore, the entity is active, just not accessible to us
            return 'active', None, None, None, ('invite' if is_invite else 'username')
        # Other ValueError cases
        LOG.error(f"Unexpected ValueError: {str(e)}", EMOJI["warning"], padding=2)
        return 'unknown', None, None, None, 'error'

    except FloodWaitError as e:
        LOG.error(f"\n\nFloodWait: waiting {e.seconds}s...", EMOJI["pause"])
        sleep(e.seconds)
        return check_entity_status(client, identifier, is_invite, expected_id)

    except Exception as e:
        LOG.error(f"Unexpected error: {type(e).__name__}: {str(e)}", EMOJI["warning"], padding=2)
        return f'error_{type(e).__name__}', None, None, None, 'error'


def check_and_display(client, identifier, is_invite, expected_id, stats, label, emoji='', padding=0):
    """
    Helper function to check status and display result.

    Returns:
        tuple: (status, restriction_details, actual_id, actual_username, method_used)
    """
    LOG.info(f"{label}...", end='\n', flush=True, padding=padding, emoji=emoji)  # end = ' ' ?
    status, restriction_details, actual_id, actual_username, method_used = check_entity_status(
        client, identifier, is_invite, expected_id
    )

    if method_used in stats['method']:
        stats['method'][method_used] += 1

    LOG.info(status, padding=padding, emoji=EMOJI.get(status, EMOJI["no_emoji"]))

    return status, restriction_details, actual_id, actual_username, method_used


def format_display_id(expected_id, identifiers, method_used):
    """
    Formats a display ID based on what method succeeded.

    Returns:
        str: Formatted display ID
    """
    if method_used == 'id':
        return f"ID:{expected_id}"
    elif method_used == 'invite':
        invite_list = identifiers if isinstance(identifiers, list) else [identifiers]
        return f"+{invite_list[0][:10]}... ({len(invite_list)} invite(s))"
    elif method_used == 'username':
        return f"@{identifiers}"
    else:
        return "???"


def check_entity_with_fallback(client, expected_id, identifiers, is_invite, stats):
    """
    Checks entity status with priority fallback: ID → Invites → Username.

    Args:
        client: TelegramClient instance
        expected_id: Entity ID (or None)
        identifiers: Username or list of invite hashes (or None)
        is_invite: Whether identifiers are invite links
        stats: Statistics dictionary to update

    Returns:
        tuple: (status, restriction_details, actual_id, actual_username, method_used, display_id)
    """
    status = None
    restriction_details = None
    actual_id = None
    actual_username = None
    method_used = None

    # PRIORITY 1: Try by ID first (most reliable)
    if expected_id:
        status, restriction_details, actual_id, actual_username, method_used = check_and_display(
            client, None, False, expected_id,
            label=f"Checking by ID: {expected_id}",
            padding=2,
            stats=stats,
            emoji=EMOJI['id']
        )

    # PRIORITY 2: Fallback to invite links (if ID failed or no ID)
    if status is None or status == 'unknown':
        if is_invite and identifiers:
            invite_list = identifiers if isinstance(identifiers, list) else [identifiers]
            LOG.info(f"  {EMOJI['fallback']} Fallback: Checking {len(invite_list)} invite(s)...")

            for idx, invite_hash in enumerate(invite_list, 1):
                status, restriction_details, actual_id, actual_username, method_used = check_and_display(
                    client, invite_hash, True, expected_id,
                    label=f"\\[{idx}/{len(invite_list)}\\] +{invite_hash}",
                    padding=4,
                    emoji=EMOJI['invite'],
                    stats=stats
                )

                if actual_id and not expected_id:
                    LOG.info(f"ID recovered: {actual_id}", padding=6, emoji=EMOJI['id'])

                if actual_username:
                    LOG.info(f"Username: @{actual_username}", padding=6, emoji=EMOJI['handle'])

                # Stop if we get a definitive answer
                if status != 'unknown':
                    break

                # Sleep between invite checks
                if idx < len(invite_list):
                    sleep(5)

    # PRIORITY 3: Fallback to username (last resort)
    if status is None or status == 'unknown':
        if not is_invite and identifiers:
            status, restriction_details, actual_id, actual_username, method_used = check_and_display(
                client, identifiers, False, expected_id,
                label=f"Fallback: Checking @{identifiers}",
                padding=2,
                emoji=EMOJI['handle'],
                stats=stats
            )

            if actual_id and not expected_id:
                LOG.info(f"ID recovered: {actual_id} (via username - unreliable)", padding=4, emoji=EMOJI['id'])

            if actual_username:
                LOG.info(f"Username: @{actual_username}", padding=4, emoji=EMOJI['handle'])

    # Final fallback (should rarely happen)
    if status is None:
        status = 'unknown'
        method_used = 'error'

    # Format display ID based on what succeeded
    display_id = format_display_id(expected_id, identifiers, method_used)

    return status, restriction_details, actual_id, actual_username, method_used, display_id


