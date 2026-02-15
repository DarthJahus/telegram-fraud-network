from telegram_mdml.telegram_mdml import TelegramEntity


def extract_telegram_identifiers(entity: TelegramEntity):
    """
    Extracts username OR invite link(s) from Telegram MDML entity.

    Args:
        entity (TelegramEntity): Telegram MDML entity

    Returns:
        tuple: (identifier, is_invite) where:
            - identifier: str (username) or list[str] (invite hashes)
            - is_invite: bool (False for username, True for invites)
    """
    # Priority 1: Check for username (non-strikethrough)
    username = entity.get_username(allow_strikethrough=False)
    if username:
        return username.value, False

    # Priority 2: Check for invites (non-strikethrough)
    invites = entity.get_invites().active()
    if invites:
        # Return list of invite hashes
        invite_hashes = [invite.hash for invite in invites]
        return invite_hashes, True

    return None, None


def get_last_status(entity: TelegramEntity):
    """
    Extracts the most recent status entry from Telegram MDML entity.
    Only returns a status if it has a valid date+time format.

    Args:
        entity (TelegramEntity): Telegram MDML entity

    Returns:
        tuple: (status, datetime, has_status_block) or (None, None, has_status_block) if no valid status found

    Note: If a status entry exists but doesn't have a valid date/time,
          it is ignored (treated as if no status exists).

    Example valid status block:
        status:
        - `active`, `2026-01-18 14:32`
        - `unknown`, `2026-01-17 10:15`
    """
    has_status_block = entity.has_field('status')
    status = entity.get_status(allow_strikethrough=False)
    if status:
        return status.value, status.date, has_status_block
    return None, None, has_status_block
