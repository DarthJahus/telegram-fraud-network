#!/usr/bin/env python3
"""
Telegram Entities Status Checker
Checks the status of Telegram entities (channels, groups, users, bots) and updates markdown files.

Usage:
  python check_status_tg.py --path . --type all [--dry-run]
  python check_status_tg.py --path . --skip-time 86400 --skip unknown banned
  python check_status_tg.py --path . --skip-time "24*60*60"

ToDo: Can we consider using more than 1 account at the same time,
      and check with every account before settling on a status?
      Should reveal helpful for groups where one account has been accepted,
      and that others can't access.
ToDo: For --get-identifiers, add:
      --only-tags tag1,tag2,...
"""

import argparse
import builtins
import re
import time
from datetime import datetime
from pathlib import Path
from telethon.sync import TelegramClient
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
from telegram_mdml.telegram_mdml import (
    TelegramEntity,
    TelegramMDMLError,
    MissingFieldError,
    InvalidFieldError,
    InvalidTypeError
)

# ============================================
# CONFIGURATION
# ============================================
DEBUG = True
API_ID = int(open('.secret/api_id', 'r', encoding='utf-8').read().strip())
API_HASH = open('.secret/api_hash', 'r', encoding='utf-8').read().strip()
SLEEP_BETWEEN_CHECKS = 20  # seconds between each check
MAX_STATUS_ENTRIES = 10  # maximum number of status entries to keep

# ============================================
# REGEX
# ============================================

REGEX_ID = re.compile(pattern=r'^id:\s*`?(\d+)`?', flags=re.MULTILINE)
REGEX_TYPE = re.compile(pattern=r'^type:\s*(\w+)', flags=re.MULTILINE)

REGEX_USERNAME_INLINE = re.compile(pattern=r'^username:\s*`?@([a-zA-Z0-9_]{5,32})`?', flags=re.MULTILINE)
REGEX_USERNAME_BLOCK_START = re.compile(pattern=r'^username:\s*$', flags=re.MULTILINE)
REGEX_USERNAME_ENTRY = re.compile(pattern=r'-\s*`@([a-zA-Z0-9_]{5,32})`')

REGEX_INVITE_INLINE = re.compile(pattern=r'^invite:\s*(?:~~)?https://t\.me/\+([a-zA-Z0-9_-]+)', flags=re.MULTILINE)
REGEX_INVITE_BLOCK_START = re.compile(pattern=r'^invite:\s*$', flags=re.MULTILINE)
REGEX_INVITE_LINK = re.compile(pattern=r'-\s*(?:~~)?https://t\.me/\+([a-zA-Z0-9_-]+)')

REGEX_STATUS_BLOCK_START = re.compile(pattern=r'^status:\s*$', flags=re.MULTILINE)
REGEX_STATUS_ENTRY_FULL = re.compile(pattern=r'^\s*-\s*`([^`]+)`\s*,\s*`(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})`',
                                     flags=re.MULTILINE)
REGEX_STATUS_BLOCK_PATTERN = re.compile(pattern=r'^\s*-\s*`[^`]+`,\s*`\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}`',
                                        flags=re.MULTILINE)
REGEX_STATUS_SUB_ITEM = re.compile(pattern=r'^\s{2,}-\s')

REGEX_NEXT_FIELD = re.compile(pattern=r'^[a-z_]+:\s', flags=re.MULTILINE)

# ============================================
# Variables & other constants
# ============================================

UI_HORIZONTAL_LINE = f"\n{60 * "•"}\n"

EMOJI = {
    'active':      "🔥",
    'banned':      "🔨",
    'deleted':     "🗑️",
    'id_mismatch': "🧩",
    'unknown':     "❓",
    'error':       "❌",
    'skip':        "⏭️",
    'id':          "🆔",
    'time':        "⏰",
    'no_emoji':    "🚫",
    'ignored':     "🙈",
    'folder':      "📂",
    'file':        "🧻",
    'dry-run':     "👓",
    'connecting':  "📡",
    'fallback':    "📨",
    'handle':      "👤",
    'stats':       "📊",
    'success':     "✅",
    'warning':     "🚨",
    'info':        "ℹ️",
    'saved':       "💾",
    'reason':      "📋",
    'text':        "💬",
    'methods':     "💊",
    'invite':      "⏳",
    'change':      "🔄",
    "pause":       "⏸️",
    "log":         "📰"
}

STATS_INIT = {
    'total': 0,
    'active': 0,
    'banned': 0,
    'deleted': 0,
    'id_mismatch': 0,
    'unknown': 0,
    'skipped': 0,
    'skipped_time': 0,
    'skipped_status': 0,
    'skipped_no_identifier': 0,
    'skipped_type': 0,
    'error': 0,
    'ignored': 0,
    'method': {
        'id': 0,
        'username': 0,
        'invite': 0
    }
}

OUT_FILE = None

# ============================================
# Helper functions
# ============================================
def get_date_time(get_date=True, get_time=True):
    dt_format = ('%Y-%m-%d' if get_date else '') + (' %H:%M' if get_time else '')
    return datetime.now().strftime(dt_format).strip()


def cut_text(text, limit=120):
    if len(text) > limit:
        return text[:(limit - 3)] + '...'
    return text


def format_console(el):
    if not isinstance(el, str):
        return el
    el = el.replace('\\[[', '').replace('\\]]', '')
    el = el.replace('\\[', '[').replace('\\]', ']')
    return el


def format_file(el):
    if not isinstance(el, str):
        return el
    return el.replace('\\[[', '[[').replace('\\]]', ']]')


def print(*args, **kwargs):
    builtins.print(*(format_console(a) for a in args), **kwargs)
    if OUT_FILE:
        builtins.print(*(format_file(a) for a in args), file=OUT_FILE, **kwargs)


def print_debug(e: Exception):
    if not DEBUG:
        return
    print('\n•••DEBUG•••')
    print(f'{type(e).__name__}')
    print(f'{str(e)}')
    print('•••••••••••\n')


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
        from telethon.tl.types import PeerChannel, PeerUser

        # Try as channel/group first (most common for your use case)
        try:
            entity = client.get_entity(PeerChannel(entity_id))
            return True, entity
        except Exception:
            # If that fails, try as user
            try:
                entity = client.get_entity(PeerUser(entity_id))
                return True, entity
            except Exception:
                # Try direct ID as last resort
                entity = client.get_entity(entity_id)
                return True, entity

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
        print(f"  {EMOJI["warning"]} Unexpected ValueError: {str(e)}")
        return 'unknown', None, None, None, 'error'

    except FloodWaitError as e:
        print(f"\n\n{EMOJI["pause"]} FloodWait: waiting {e.seconds}s...")
        time.sleep(e.seconds)
        return check_entity_status(client, identifier, is_invite, expected_id)

    except Exception as e:
        print(f"  {EMOJI["warning"]} Unexpected error: {type(e).__name__}: {str(e)}")
        return f'error_{type(e).__name__}', None, None, None, 'error'


# ============================================
# MARKDOWN FILE PARSING
# ============================================

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


def should_skip_entity(entity, skip_time_seconds, skip_statuses, skip_unknown=True):
    """
    Determines if an entity should be skipped based on its last status.

    Args:
        entity (TelegramEntity): Telegram MDML entity
        skip_time_seconds (int or None): Skip if checked within this many seconds
        skip_statuses (list or None): Skip if last status is in this list
        skip_unknown (default: True): Skip when last_stats is Unknown

    Returns:
        tuple: (should_skip, reason) where reason explains why it was skipped
    """
    last_status, last_datetime, has_status_block = get_last_status(entity)

    if last_status is None:
        # No previous status, don't skip
        return False, None

    # Check if we should skip based on status
    if skip_statuses and last_status in skip_statuses:
        return True, f"last status is '{last_status}' (exception)"

    # Check if we should skip based on time
    # IMPORTANT: Never skip 'unknown' status based on time (always re-check)
    if skip_time_seconds is not None and not skip_unknown or last_status != 'unknown':
        time_since_check = datetime.now() - last_datetime
        if time_since_check.total_seconds() < skip_time_seconds:
            hours = int(time_since_check.total_seconds() / 3600)
            mins = int((time_since_check.total_seconds() % 3600) / 60)
            return True, f"checked {hours}h {mins}m ago (status: {last_status})"

    return False, None

# ============================================
# MARKDOWN FILE UPDATING
# ============================================

def write_id_to_md(file_path, entity_id):
    """
    Writes the entity ID at the beginning of the markdown file.
    Only writes if no ID field exists yet.

    Insertion logic:
    - If YAML frontmatter exists (---...---), insert after it with blank line
    - Otherwise, insert at the very beginning (line 0)

    Args:
        file_path: Path to markdown file
        entity_id: Entity ID to write

    Returns:
        bool: True if ID was written, False if ID already exists or error
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check if ID already exists
    if REGEX_ID.search(content):
        return False

    lines = content.split('\n')

    # Detect YAML frontmatter
    insert_pos = 0  # Default: very beginning

    if len(lines) > 0 and lines[0].strip() == '---':
        # Look for closing ---
        for i in range(1, len(lines)):
            if lines[i].strip() == '---':
                # Insert after the closing --- and a blank line
                insert_pos = i + 1
                # Add blank line if not already present
                if insert_pos < len(lines) and lines[insert_pos].strip() != '':
                    lines.insert(insert_pos, '')
                    insert_pos += 1
                break

    # Insert the ID field
    lines.insert(insert_pos, f"id: `{entity_id}`")

    # Write back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return True


def update_status_in_md(file_path, new_status, restriction_details=None):
    """
    Updates the status block in a markdown file by adding a new status entry.
    Keeps a maximum of MAX_STATUS_ENTRIES entries.
    When pruning, removes the middle entry to preserve both recent and oldest entries.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 1. Find the status: block
    status_line_idx = None
    for i, line in enumerate(lines):
        if REGEX_STATUS_BLOCK_START.match(line.strip()):
            status_line_idx = i
            break

    if status_line_idx is None:
        print(f"  {EMOJI["warning"]} No 'status:' block found in {file_path.name}")
        return False

    # 2. Find the next field (end of status block)
    next_field_idx = None
    for i in range(status_line_idx + 1, len(lines)):
        # Next field starts with word characters followed by ':'
        if REGEX_NEXT_FIELD.match(lines[i]):
            next_field_idx = i
            break

    # If no next field found, status block goes to end of file
    if next_field_idx is None:
        next_field_idx = len(lines)

    # 3. Extract existing status entries from the block
    status_block_lines = lines[status_line_idx + 1:next_field_idx]
    existing_entries = []
    current_entry = []

    for line in status_block_lines:
        # Check if this is a new status entry (has date/time)
        if REGEX_STATUS_BLOCK_PATTERN.match(line):
            # Save previous entry if exists
            if current_entry:
                existing_entries.append(current_entry)
            # Start new entry
            current_entry = [line]
        # Check if this is a sub-item (part of current entry)
        elif REGEX_STATUS_SUB_ITEM.match(line) and current_entry:
            current_entry.append(line)
        # Else: ignore malformed lines

    # Don't forget the last entry
    if current_entry:
        existing_entries.append(current_entry)

    # 4. Create new status entry
    new_entry = [f"- `{new_status}`, `{get_date_time()}`\n"]

    if restriction_details:
        if 'reason' in restriction_details and restriction_details['reason']:
            new_entry.append(f"  - reason: `{restriction_details['reason']}`\n")
        if 'text' in restriction_details and restriction_details['text']:
            text = restriction_details['text'].replace('`', "'")
            new_entry.append(f"  - text: `{text}`\n")

    # 5. Prune old entries if needed
    if len(existing_entries) >= MAX_STATUS_ENTRIES - 1:
        middle_index = len(existing_entries) // 2
        existing_entries.pop(middle_index)

    # 6. Reconstruct file: before + status: + new entry + old entries + after
    new_lines = []
    new_lines.extend(lines[:status_line_idx + 1])  # Everything before and including 'status:'
    new_lines.extend(new_entry)  # New status entry
    for entry in existing_entries:  # Existing entries
        new_lines.extend(entry)
    new_lines.append('\n')
    new_lines.extend(lines[next_field_idx:])  # Everything after status block

    # 7. Write back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

    return True


# ============================================
# REPORTING
# ============================================

def print_dry_run_summary(results):
    """
    Prints a summary of what would be changed in dry-run mode.

    Args:
        results (list): List of result dictionaries
    """
    if not results:
        return

    print("\n" + UI_HORIZONTAL_LINE)
    print(f"{EMOJI["dry-run"]} DRY-RUN SUMMARY - Changes to apply:")

    # Group by status
    for status_type in ['active', 'banned', 'deleted', 'unknown']:
        filtered = [r for r in results if r['status'] == status_type]
        if filtered:
            print(f"\n{filtered[0]['emoji']} {status_type.upper()} ({len(filtered)}):")
            for r in filtered:
                print(f"  • {r['file']}: {r['identifier']}")
                print(f"    → - `{r['status']}`, `{r['timestamp']}`")
                if r.get('restriction_details'):
                    details = r['restriction_details']
                    if 'reason' in details:
                        print(f"      - reason: `{details['reason']}`")
                    if 'text' in details:
                        text = details['text'][:80] + '...' if len(details['text']) > 80 else details['text']
                        print(f"      - text: `{text}`")

    # Errors
    errors = [r for r in results if r['status'].startswith('error_')]
    if errors:
        print()
        print(f"{EMOJI["error"]} ERRORS ({len(errors)}):")
        for r in errors:
            print(f"  • {r['file']}: {r['identifier']} → {r['status']}")

    print(f"{EMOJI["info"]} To apply these changes, run again without --dry-run")
    print(UI_HORIZONTAL_LINE)


def parse_time_expression(expr):
    """
    Parses a time expression that can be either a number or a Python expression.

    Args:
        expr (str): Time expression (e.g., "86400" or "24*60*60")

    Returns:
        int: Number of seconds

    Raises:
        ValueError: If the expression is invalid
    """
    try:
        # Try to evaluate as a Python expression (allows "24*60*60")
        result = eval(expr, {"__builtins__": {}}, {})
        if not isinstance(result, (int, float)):
            raise ValueError("Expression must evaluate to a number")
        return int(result)
    except Exception as e:
        raise ValueError(f"Invalid time expression '{expr}': {e}")


# ============================================
# MAIN
# ============================================

def build_arg_parser():
    parser = argparse.ArgumentParser(
        description='Check Telegram entities status and update markdown files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
    Examples:
      # Check all entities
      %(prog)s --path .

      # Skip entities checked in the last 24 hours
      %(prog)s --path . --skip-time 86400
      %(prog)s --path . --skip-time "24*60*60"

      # Skip entities with 'unknown' or 'banned' status
      %(prog)s --path . --skip unknown banned

      # Combine both: skip if checked recently OR if unknown/banned
      %(prog)s --path . --skip-time "24*60*60" --skip unknown banned

      # Check only channels, skip those checked in the last 12 hours
      %(prog)s --path . --type channel --skip-time "12*60*60"

      # Check all but don't update files for 'unknown' status
      %(prog)s --path . --ignore unknown

      # Check all but ignore both 'unknown' and 'banned'
      %(prog)s --path . --ignore unknown banned
            """
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
        choices=['all', 'channel', 'group', 'user', 'bot'],
        default='all',
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
        '--md-tasks',
        action='store_true',
        help="With --get-invites: print results as markdown tasks"
    )
    parser.add_argument(
        '--valid-only',
        action='store_true',
        help="With --get-invites: only print valid invites"
    )
    parser.add_argument(
        '--get-identifiers',
        nargs='?',
        const='all',
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
        '--get-info',
        action='store_true',
        help='Get full information about a Telegram entity and output as MDML'
    )
    parser.add_argument(
        '--by-id',
        type=int,
        metavar='ID',
        help='Entity ID to retrieve information for (use with --get-info)'
    )
    parser.add_argument(
        '--by-username',
        type=str,
        metavar='USERNAME',
        help='Username to retrieve information for (use with --get-info, without @)'
    )
    parser.add_argument(
        '--by-invite',
        type=str,
        metavar='HASH',
        help='Invite hash to retrieve information for (use with --get-info)'
    )

    return parser


def print_stats(stats):
    print("\n" + UI_HORIZONTAL_LINE)
    print(f"{EMOJI["stats"]} RESULTS")
    print(f"Total checked:  {stats['total']}")
    print(f"{EMOJI.get("active")     } Active:      {stats['active']     }")
    print(f"{EMOJI.get("banned")     } Banned:      {stats['banned']     }")
    print(f"{EMOJI.get("deleted")    } Deleted:     {stats['deleted']    }")
    print(f"{EMOJI.get("id_mismatch")} ID Mismatch: {stats['id_mismatch']}")
    print(f"{EMOJI.get("unknown")    } Unknown:     {stats['unknown']    }")
    print(f"{EMOJI.get("error")      } Errors:      {stats['error']      }")
    print()
    print(f"{EMOJI["skip"]} Skipped (total):      {stats['skipped']}")
    if stats['skipped_time'] > 0:
        print(f"   └─ Recently checked:  {stats['skipped_time']}")
    if stats['skipped_status'] > 0:
        print(f"   └─ By status:         {stats['skipped_status']}")
    if stats['skipped_no_identifier'] > 0:
        print(f"   └─ No identifier:     {stats['skipped_no_identifier']}")
    if stats['skipped_type'] > 0:
        print(f"   └─ Wrong type:        {stats['skipped_type']}")
    if stats['ignored'] > 0:
        print()
        print(f"{EMOJI["ignored"]} total:      {stats['ignored']}")
    print()
    if stats['method']:
        print(f"{EMOJI["methods"]} Methods used:")
        if stats['method']['id'] > 0:
            print(f"   └─ By ID:        {stats['method']['id']}")
        if stats['method']['username'] > 0:
            print(f"   └─ By username:  {stats['method']['username']}")
        if stats['method']['invite'] > 0:
            print(f"   └─ By invite:    {stats['method']['invite']}")
    print(UI_HORIZONTAL_LINE)


def print_no_status_block(no_status_block_results):
    print(UI_HORIZONTAL_LINE)
    print(f"{EMOJI["warning"]} FILES WITHOUT 'status:' BLOCK (STATUS DETECTED)")
    for item in no_status_block_results:
        print(f"• \\[[{item['file']}\\]] → {item['emoji']} {item['status']}")
    print(UI_HORIZONTAL_LINE)


def print_status_changed_files(status_changed_files):
    print("\n" + "!" * 60)
    print(f"{EMOJI["change"]} FILES WITH STATUS CHANGE (RENAME IN OBSIDIAN)")
    for item in status_changed_files:
        print(f"• \\[[{item['file']}\\]] : {item['old']} → {item['new']}")
    print(UI_HORIZONTAL_LINE)


def print_recovered_ids(recovered_ids):
    """
    Prints a summary of recovered entity IDs.

    Args:
        recovered_ids (list): List of dicts with 'file', 'id', 'method', 'written'
    """
    if not recovered_ids:
        return

    print("\n" + UI_HORIZONTAL_LINE)
    print(f"{EMOJI['id']} RECOVERED IDs ({len(recovered_ids)})")

    # Group by method
    by_invite = [r for r in recovered_ids if r['method'] == 'invite']
    by_username = [r for r in recovered_ids if r['method'] == 'username']

    if by_invite:
        print(f"\n✅ Via INVITE (reliable):")
        for item in by_invite:
            written_mark = "✅" if item.get('written') else "⚠️"
            print(f"  {written_mark} \\[[{item['file']}\\]] → id: `{item['id']}`")

        written_count = sum(1 for r in by_invite if r.get('written'))
        if written_count > 0:
            print(f"\n  ✅ {written_count} ID(s) written to files")
        not_written = len(by_invite) - written_count
        if not_written > 0:
            print(f"  ⚠️  {not_written} ID(s) not written (ID already exists or --write-id not enabled)")

    if by_username:
        print(f"\n⚠️  Via USERNAME (unreliable - DO NOT write):")
        for item in by_username:
            print(f"  • \\[[{item['file']}\\]] → id: `{item['id']}`")
        print(f"\n  ⚠️  These IDs were recovered via username.")
        print(f"     Verify manually before adding them to files!")

    if by_invite:
        print(f"{EMOJI['info']} IDs recovered via invite are reliable and permanent.")
        print(f"{EMOJI['info']} Use them for faster future checks.")
    print(UI_HORIZONTAL_LINE)


def print_discovered_usernames(discovered_usernames):
    """
    Prints a summary of discovered/changed usernames.

    Args:
        discovered_usernames (list): List of dicts with 'file', 'old_username', 'new_username', 'status'
    """
    if not discovered_usernames:
        return

    print("\n" + UI_HORIZONTAL_LINE)
    print(f"{EMOJI['handle']} DISCOVERED/CHANGED USERNAMES ({len(discovered_usernames)})")

    # Group by status
    discovered = [u for u in discovered_usernames if u['status'] == 'discovered']
    changed = [u for u in discovered_usernames if u['status'] == 'changed']

    if discovered:
        print(f"\n✨ DISCOVERED (new usernames):")
        for item in discovered:
            print(f"  • \\{item['file']}\\]] → @{item['new_username']}")
        print(f"\n  {EMOJI["info"]}  {len(discovered)} username(s) discovered")

    if changed:
        print(f"\n🔄 CHANGED (username updates):")
        for item in changed:
            print(f"  • \\[[{item['file']}\\]] : @{item['old_username']} → @{item['new_username']}")
        print(f"\n  ⚠️  {len(changed)} username(s) changed")

    print(f"{EMOJI['warning']} Usernames can change frequently - verify before updating files!")
    print(f"{EMOJI['info']} Consider manually updating the markdown files with new usernames.")
    print(UI_HORIZONTAL_LINE)


def check_and_display(client, identifier, is_invite, expected_id, label, stats):
    """
    Helper function to check status and display result.

    Returns:
        tuple: (status, restriction_details, actual_id, actual_username, method_used)
    """
    print(f"{label}...", end=' ', flush=True)
    status, restriction_details, actual_id, actual_username, method_used = check_entity_status(
        client, identifier, is_invite, expected_id
    )

    if method_used in stats['method']:
        stats['method'][method_used] += 1

    emoji = EMOJI.get(status, EMOJI["no_emoji"])
    print(f"{emoji} {status}")

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
            f"  {EMOJI.get('id')} Checking by ID: {expected_id}",
            stats
        )

    # PRIORITY 2: Fallback to invite links (if ID failed or no ID)
    if status is None or status == 'unknown':
        if is_invite and identifiers:
            invite_list = identifiers if isinstance(identifiers, list) else [identifiers]
            print(f"  {EMOJI['fallback']} Fallback: Checking {len(invite_list)} invite(s)...")

            for idx, invite_hash in enumerate(invite_list, 1):
                status, restriction_details, actual_id, actual_username, method_used = check_and_display(
                    client, invite_hash, True, expected_id,
                    f"    {EMOJI['invite']} \\[{idx}/{len(invite_list)}\\] +{invite_hash}",
                    stats
                )

                if actual_id and not expected_id:
                    print(f"      {EMOJI['id']} ID recovered: {actual_id}")

                if actual_username:
                    print(f"      {EMOJI['handle']} Username: @{actual_username}")

                # Stop if we get a definitive answer
                if status != 'unknown':
                    break

                # Sleep between invite checks
                if idx < len(invite_list):
                    time.sleep(5)

    # PRIORITY 3: Fallback to username (last resort)
    if status is None or status == 'unknown':
        if not is_invite and identifiers:
            status, restriction_details, actual_id, actual_username, method_used = check_and_display(
                client, identifiers, False, expected_id,
                f"  {EMOJI['handle']} Fallback: Checking @{identifiers}",
                stats
            )

            if actual_id and not expected_id:
                print(f"    {EMOJI['id']} ID recovered: {actual_id} (via username - unreliable)")

            if actual_username:
                print(f"    {EMOJI['handle']} Username: @{actual_username}")

    # Final fallback (should rarely happen)
    if status is None:
        status = 'unknown'
        method_used = 'error'

    # Format display ID based on what succeeded
    display_id = format_display_id(expected_id, identifiers, method_used)

    return status, restriction_details, actual_id, actual_username, method_used, display_id


def process_and_update_file(md_file, status, restriction_details, actual_id, expected_id, last_status, should_ignore, is_dry_run):
    """
    Displays additional info, updates file if needed, and prepares result data.

    Args:
        md_file: Path to markdown file
        status: Current status
        restriction_details: Restriction details (if any)
        actual_id: Actual entity ID (for id_mismatch)
        expected_id: Expected entity ID
        last_status: Previous status
        should_ignore: Whether to ignore this status
        is_dry_run: Whether in dry-run mode

    Returns:
        tuple: (should_track_change, was_updated)
            - should_track_change: True if status changed
            - was_updated: True if file was actually updated
    """
    # Display additional info
    if status == 'id_mismatch' and actual_id:
        print(f"  {EMOJI["id_mismatch"]} Expected ID: {expected_id}, found ID: {actual_id}")

    if last_status is not None and last_status != status:
        print(f"  {EMOJI["change"]} STATUS CHANGE: {last_status} → {status}")

    if restriction_details:
        if 'reason' in restriction_details:
            print(f"  {EMOJI["reason"]} Reason: {restriction_details['reason']}")
        if 'text' in restriction_details:
            text_preview = cut_text(restriction_details['text'], 120-11)
            print(f"  {EMOJI["text"]} Text: {text_preview}")

    # Handle file updates
    should_track_change = False
    was_updated = False

    if should_ignore:
        print(f"  {EMOJI["ignored"]} Ignoring status '{status}' (not updating file)")
    else:
        # Track status change
        if last_status != status:
            should_track_change = True

        # Update file
        if not is_dry_run:
            if update_status_in_md(md_file, status, restriction_details):
                print(f"  {EMOJI["saved"]} File updated")
                was_updated = True
        else:
            # Show what WOULD be written
            print(f"  {EMOJI["dry-run"]} Would add:")
            print(f"    `{status}`, `{get_date_time()}`")
            if restriction_details:
                if 'reason' in restriction_details:
                    print(f"    - reason: `{restriction_details['reason']}`")
                if 'text' in restriction_details:
                    print(f"    - text: `{restriction_details['text'][:50]}...`")

    return should_track_change, was_updated


def print_identifiers(identifiers_list, md_tasks=True, valid_only=False, clean=False):
    if not identifiers_list:
        return

    md_check_list = ''
    if md_tasks:
        md_check_list = '- [ ] '

    # Print results
    if len(identifiers_list) > 1:
        print(f"\n{EMOJI['invite']} Found {len(identifiers_list)} identifiers:\n")

    for ident in identifiers_list:
        type_indicator = ' ' + (EMOJI['invite'] if "+" in ident['full_link'] else EMOJI['handle'])
        if ident['valid'] is True:
            print(f"{md_check_list}{EMOJI["active"]}{type_indicator} {ident['full_link']}")
            if not clean:
                if ident['user_id']:
                    print(f"  {EMOJI["id"]      } {ident['user_id']}")
                print(f"  {EMOJI["file"]    } {ident['file']}")
                print()
        elif ident['valid'] is False and not valid_only:
            print(f"{md_check_list}{EMOJI["no_emoji"]}{type_indicator} {ident['full_link']}")
            if not clean:
                print(f"  {EMOJI["file"]    } {ident['file']}")
                print(f"  {EMOJI["text"]    } {ident['reason']}")
                print(f"  {EMOJI["text"]    } {ident['message']}")
                print()
        elif ident['valid'] is None:  # valid is None, because we haven't checked for validity
            print(f"{md_check_list}{type_indicator} {ident['full_link']}")
            if not clean:
                print(f"  {EMOJI["file"]    } {ident['file']}")
                print()


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
                print_debug(Exception("SHOULD NEVER HAVE HAPPENED"))
        except ValueError as e:
            message = str(e)
        except Exception as e:
            print_debug(e)
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
        print(f"{EMOJI['pause']} FloodWait: waiting {e.seconds}s...")
        time.sleep(e.seconds)
        return validate_invite(client, invite_hash)

    except Exception as e:
        print_debug(e)
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
        print(f"  {EMOJI['pause']} FloodWait: waiting {e.seconds}s...")
        time.sleep(e.seconds)
        return validate_handle(client, username)
    except Exception as e:
        print_debug(e)
        return False, None, 'ERROR', f'{type(e).__name__}: {str(e)}'


def connect_to_telegram(user):
    # Load phone number for user
    session_dir = Path('.secret')
    session_dir.mkdir(exist_ok=True)
    mobile_file = session_dir / f'{user}.mobile'

    if not mobile_file.exists():
        print(f"{EMOJI["error"]} Mobile file not found: {mobile_file}")
        print(f"  Create it with:")
        print(f"    echo '+1234567890' > {mobile_file}")
        return

    phone = mobile_file.read_text(encoding='utf-8').strip()

    # Connect to Telegram
    session_file = session_dir / user
    print(f"{EMOJI["handle"]} User: {user}")
    print(f"{EMOJI["connecting"]} Connecting to Telegram...")
    client = TelegramClient(str(session_file), API_ID, API_HASH)
    client.start(phone=phone)
    print(f"{EMOJI["success"]} Connected!\n")
    return client


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
                    time.sleep(SLEEP_BETWEEN_CHECKS)  # Rate limiting
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
                        time.sleep(SLEEP_BETWEEN_CHECKS)
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


def full_check(client, args, ignore_statuses, md_files, skip_time_seconds):
    # Statistics
    stats = STATS_INIT.copy()
    # Store results for dry-run summary
    results = []
    status_changed_files = []
    no_status_block_results = []
    recovered_ids = []  # List of {file, id, method, written}
    discovered_usernames = []  # List of {file, old_username, new_username, status}
    try:
        for md_file in md_files:
            # parsing the file through MDML
            try:
                entity = TelegramEntity.from_file(md_file)
                print()
                print(f"{EMOJI["file"]} \\[[{md_file.name}\\]]")

                # Check type filter
                try:
                    entity_type = entity.get_type()
                except (InvalidTypeError, MissingFieldError):
                    entity_type = None
                except Exception as e:
                    print(f"{EMOJI['error']} Error: {e}")
                    entity_type = None

                if args.type != 'all' and entity_type != args.type:
                    stats['skipped'] += 1
                    stats['skipped_type'] += 1
                    continue

                # Extract ALL identifiers upfront
                try:
                    expected_id = entity.get_id()
                except InvalidFieldError:
                    expected_id = None
                except Exception as e:
                    print(f"{EMOJI['error']} Error: {e}")
                    expected_id = None

                identifiers, is_invite = extract_telegram_identifiers(entity)

                # If no ID AND no identifiers, skip entirely
                if not expected_id and not identifiers:
                    print(f"  {EMOJI["skip"]} Skipped: No identifier found")
                    stats['skipped'] += 1
                    stats['skipped_no_identifier'] += 1
                    continue

                # Get last status info
                last_status, last_datetime, has_status_block = get_last_status(entity)

                # Check if we should skip based on last status
                should_skip, skip_reason = should_skip_entity(entity, skip_time_seconds, args.skip, not args.no_skip_unknown)
                if should_skip:
                    print(f"  {EMOJI["skip"]} Skipped: ({skip_reason})")
                    stats['skipped'] += 1
                    if 'checked' in skip_reason and 'ago' in skip_reason:
                        stats['skipped_time'] += 1
                    elif 'last status' in skip_reason:
                        stats['skipped_status'] += 1
                    continue

                # Check entity status with priority fallback
                status, restriction_details, actual_id, actual_username, method_used, display_id = check_entity_with_fallback(
                    client, expected_id, identifiers, is_invite, stats
                )

                # Check and write the retrieved ID
                if actual_id and not expected_id:
                    id_written = False

                    # Write ID retrieved via invite, if --write-id
                    if method_used == 'invite' and args.write_id and not args.dry_run:
                        if write_id_to_md(md_file, actual_id):
                            print(f"  {EMOJI['saved']} ID written to file: `{actual_id}`")
                            id_written = True
                        else:
                            print(f"  {EMOJI['info']} ID already present in file.")

                    # Add to list of retrieved ID
                    recovered_ids.append({
                        'file': md_file.name,
                        'id': actual_id,
                        'method': method_used,
                        'written': id_written
                    })

                # Track discovered / changed usernames
                if actual_username:
                    username = entity.get_username(allow_strikethrough=False)
                    if username:
                        existing_username = username.value  # username without @
                    else:
                        existing_username = None

                    # Cas 1 : Discovered username not in MDML
                    if not existing_username:
                        print(f"  {EMOJI['handle']} Username discovered: @{actual_username}")
                        discovered_usernames.append({
                            'file': md_file.name,
                            'old_username': None,
                            'new_username': actual_username,
                            'status': 'discovered'
                        })

                    # Cas 2 : Username has changed AND is different from username in MDML
                    elif existing_username.lower() != actual_username.lower():
                        print(f"  {EMOJI['change']} Username changed: @{existing_username} → @{actual_username}")
                        discovered_usernames.append({
                            'file': md_file.name,
                            'old_username': existing_username,
                            'new_username': actual_username,
                            'status': 'changed'
                        })

                # Update statistics
                stats['total'] += 1
                if status == 'active':
                    stats['active'] += 1
                elif status == 'banned':
                    stats['banned'] += 1
                elif status == 'deleted':
                    stats['deleted'] += 1
                elif status == 'id_mismatch':
                    stats['id_mismatch'] += 1
                elif status == 'unknown':
                    stats['unknown'] += 1
                else:
                    stats['error'] += 1

                # Process result and update file if needed
                should_ignore = ignore_statuses and status in ignore_statuses
                if should_ignore:
                    stats['ignored'] += 1

                should_track_change, _ = process_and_update_file(
                    md_file, status, restriction_details, actual_id,
                    expected_id, last_status,
                    should_ignore, args.dry_run
                )

                # Store result for reports
                result = {
                    'file': md_file.name,
                    'identifier': display_id,
                    'status': status,
                    'timestamp': get_date_time(),
                    'emoji': EMOJI.get(status, EMOJI["no_emoji"]),
                    'restriction_details': restriction_details
                }
                results.append(result)

                # Track files without status block
                if not has_status_block:
                    no_status_block_results.append(result)

                # Track status changes
                if should_track_change:
                    status_changed_files.append({
                        'file': md_file.name,
                        'old': last_status,
                        'new': status
                    })

                # Sleep between checks to avoid rate limiting
                if md_file != md_files[-1]:
                    time.sleep(SLEEP_BETWEEN_CHECKS)
            except FileNotFoundError:
                print("File not found.")
            except TelegramMDMLError:
                print("Parsing failed.")
            except Exception as e:
                print("Failed to read MDML entity from file.")
                print_debug(e)
    except KeyboardInterrupt:
        client.disconnect()
        exit(0)
    finally:
        # Always disconnect, even if there's an error
        client.disconnect()
    # Final statistics
    print_stats(stats)
    # Dry-run summary
    if args.dry_run:
        print_dry_run_summary(results)
    if status_changed_files:
        print_status_changed_files(status_changed_files)
    if no_status_block_results:
        print_no_status_block(no_status_block_results)
    if recovered_ids:
        print_recovered_ids(recovered_ids)
    if discovered_usernames:
        print_discovered_usernames(discovered_usernames)


def fetch_entity_info(client, by_id=None, by_username=None, by_invite=None):
    """
    Fetches comprehensive information about a Telegram entity.

    Args:
        client: TelegramClient instance
        by_id: Entity ID (int)
        by_username: Username (str, without @)
        by_invite: Invite hash (str)

    Returns:
        dict: Entity information or None on error
    """
    from telethon.tl.functions.channels import GetFullChannelRequest, GetParticipantsRequest
    from telethon.tl.functions.users import GetFullUserRequest
    from telethon.tl.types import (
        Channel, User, Chat, PeerChannel, PeerUser, PeerChat,
        ChannelParticipantsAdmins, ChannelParticipantCreator
    )

    # Determine which method to use
    entity = None
    try:
        if by_id:
            print(f"{EMOJI['id']} Fetching entity by ID: {by_id}...", file=__import__('sys').stderr)
            # Try different peer types
            try:
                entity = client.get_entity(PeerChannel(by_id))
            except:
                try:
                    entity = client.get_entity(PeerUser(by_id))
                except:
                    try:
                        entity = client.get_entity(PeerChat(by_id))
                    except:
                        entity = client.get_entity(by_id)

        elif by_username:
            print(f"{EMOJI['handle']} Fetching entity by username: @{by_username}...", file=__import__('sys').stderr)
            entity = client.get_entity(by_username)

        elif by_invite:
            print(f"{EMOJI['invite']} Fetching entity by invite: +{by_invite}...", file=__import__('sys').stderr)
            entity = client.get_entity(f'https://t.me/+{by_invite}')

        else:
            print(f"{EMOJI['error']} No identifier provided", file=__import__('sys').stderr)
            return None

        if not entity:
            print(f"{EMOJI['error']} Could not retrieve entity", file=__import__('sys').stderr)
            return None

        print(f"{EMOJI['success']} Entity retrieved!\n", file=__import__('sys').stderr)

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

        # Username
        if hasattr(entity, 'username') and entity.username:
            info['username'] = entity.username

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
            info['mobile'] = entity.phone

        # Created date and first message
        if isinstance(entity, Channel):
            try:
                messages = client.get_messages(entity, limit=1, reverse=True)
                if messages:
                    first_msg = messages[0]
                    info['created_date'] = first_msg.date.strftime('%Y-%m-%d')
                    info['created_msg_id'] = first_msg.id
            except:
                pass

        # Linked channel/discussion
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
        except:
            pass

        return info

    except Exception as e:
        print(f"{EMOJI['error']} Error retrieving entity: {e}", file=__import__('sys').stderr)
        print_debug(e)
        return None


def format_entity_mdml(info):
    """
    Formats entity information as MDML using the MDML library.

    Args:
        info: dict returned by fetch_entity_info()

    Returns:
        str: MDML formatted text
    """
    from mdml.models import Document, Field, FieldValue
    from telethon.tl.types import Channel, Chat, User

    if not info:
        return ""

    now = get_date_time()
    now_date, now_time = now.split(' ')

    # Create Document with frontmatter
    doc = Document(raw_content='')
    if info.get('type'):
        doc.frontmatter['type'] = info['type']

    # ID
    doc.fields['id'] = Field(
        name='id',
        is_list=False,
        values=[FieldValue(value=str(info['id']))],
        raw_content=''
    )

    # Status
    doc.fields['status'] = Field(
        name='status',
        is_list=True,
        values=[FieldValue(value='active', date=now_date, time=now_time)],
        raw_content=''
    )

    # Discovered
    doc.fields['discovered'] = Field(
        name='discovered',
        is_list=False,
        values=[FieldValue(value=now)],
        raw_content=''
    )

    # Username
    if info.get('username'):
        doc.fields['username'] = Field(
            name='username',
            is_list=False,
            values=[FieldValue(
                value=f"@{info['username']}",
                link_url=f"https://t.me/{info['username']}"
            )],
            raw_content=''
        )

    # Name
    if info.get('name'):
        doc.fields['name'] = Field(
            name='name',
            is_list=False,
            values=[FieldValue(value=info['name'])],
            raw_content=''
        )

    # Bio
    if info.get('bio'):
        lines = [line.strip() for line in info['bio'].split('\n') if line.strip()]
        if lines:
            doc.fields['bio'] = Field(
                name='bio',
                is_list=False,
                values=[FieldValue(
                    value='',
                    is_array=True,
                    array_values=lines
                )],
                raw_content=''
            )

    # Mobile
    if info.get('mobile'):
        doc.fields['mobile'] = Field(
            name='mobile',
            is_list=False,
            values=[FieldValue(value=info['mobile'])],
            raw_content=''
        )

    # Activity (empty list)
    doc.fields['activity'] = Field(
        name='activity',
        is_list=False,
        values=[],
        raw_content=''
    )

    # Invite
    if info.get('by_invite'):
        doc.fields['invite'] = Field(
            name='invite',
            is_list=False,
            values=[FieldValue(value=f"https://t.me/+{info['by_invite']}")],
            raw_content=''
        )

    # Only for channels/groups, not users
    entity = info.get('entity')
    if not isinstance(entity, User):
        # Joined (empty list)
        doc.fields['joined'] = Field(
            name='joined',
            is_list=True,
            values=[],
            raw_content=''
        )

        # Created
        if info.get('created_date'):
            entity_id = info['id']
            msg_id = info.get('created_msg_id', 1)
            created_link = f"https://t.me/c/{entity_id}/{msg_id}"

            if msg_id == 1:
                doc.fields['created'] = Field(
                    name='created',
                    is_list=False,
                    values=[FieldValue(
                        value=info['created_date'],
                        link_url=created_link
                    )],
                    raw_content=''
                )
            else:
                doc.fields['created'] = Field(
                    name='created',
                    is_list=False,
                    values=[FieldValue(
                        value=f"before {info['created_date']}",
                        is_raw=True,
                        link_url=created_link
                    )],
                    raw_content=''
                )
        else:
            doc.fields['created'] = Field(
                name='created',
                is_list=True,
                values=[],
                raw_content=''
            )

    # Linked channel (for supergroups)
    if isinstance(entity, Channel) and entity.megagroup:
        if info.get('linked_chat_id'):
            doc.fields['linked channel'] = Field(
                name='linked channel',
                is_list=False,
                values=[FieldValue(
                    value=f"tg_{info['linked_chat_id']}",
                    is_wiki_link=True,
                    wiki_link=f"tg_{info['linked_chat_id']}"
                )],
                raw_content=''
            )

    # Members/Subscribers
    if info.get('count'):
        if isinstance(entity, Channel):
            if entity.megagroup:
                count_field = "members"
            elif entity.broadcast:
                count_field = "subscribers"
            else:
                count_field = "members"
        elif isinstance(entity, Chat):
            count_field = "members"
        else:
            count_field = None

        if count_field:
            doc.fields[count_field] = Field(
                name=count_field,
                is_list=True,
                values=[FieldValue(
                    value=str(info['count']),
                    date=now_date,
                    time=now_time
                )],
                raw_content=''
            )

    # Discussion (for channels)
    if isinstance(entity, Channel) and entity.broadcast:
        if info.get('linked_chat_id'):
            doc.fields['discussion'] = Field(
                name='discussion',
                is_list=False,
                values=[FieldValue(
                    value=f"tg_{info['linked_chat_id']}",
                    is_wiki_link=True,
                    wiki_link=f"tg_{info['linked_chat_id']}"
                )],
                raw_content=''
            )

    # Owner
    if info.get('owner'):
        doc.fields['owner'] = Field(
            name='owner',
            is_list=False,
            values=[FieldValue(
                value=f"tg_{info['owner']}",
                is_wiki_link=True,
                wiki_link=f"tg_{info['owner']}"
            )],
            raw_content=''
        )

    # Admins - Liste MDML avec wikilinks
    if info.get('admins'):
        admin_values = []
        for uid in info['admins']:
            admin_values.append(FieldValue(
                value=f"tg_{uid}",
                is_wiki_link=True,
                wiki_link=f"tg_{uid}"
            ))

        doc.fields['admins'] = Field(
            name='admins',
            is_list=True,
            values=admin_values,
            raw_content=''
        )

    return doc
    import json
    return json.dumps(doc.to_dict(),indent='\t')


def get_entity_info(client, by_id=None, by_username=None, by_invite=None):
    """
    Main function to fetch and output entity information as MDML.
    """
    try:
        info = fetch_entity_info(client, by_id=by_id, by_username=by_username, by_invite=by_invite)
        if info:
            mdml = format_entity_mdml(info)
            return mdml
        else:
            print(f"{EMOJI['error']} Failed to fetch entity information", file=__import__('sys').stderr)
    except Exception as e:
        print(f"{EMOJI['error']} Error generating MDML: {e}", file=__import__('sys').stderr)
        print_debug(e)
    return


def validate_args(args):
    if args.no_skip and not (args.get_identifiers and args.invites_only):
        print(f"{EMOJI['warning']} --no-skip can only be used with --get-identifiers --invites-only")
    if args.continuous and not args.get_identifiers:
        print(f"{EMOJI['warning']} --continuous can only be used with --get-identifiers")
    if args.md_tasks and not args.get_identifiers:
        print(f"{EMOJI['warning']} --md-tasks can only be used with --get-identifiers")
    if args.valid_only and not args.get_identifiers:
        print(f"{EMOJI['warning']} --valid-only can only be used with --get-identifiers")
    if args.clean and not args.get_identifiers:
        print(f"{EMOJI['warning']} --clean can only be used with --get-identifiers")
    if args.include_users and not args.get_identifiers:
        print(f"{EMOJI['warning']} --include-users can only be used with --get-identifiers")
    # Validate --get-info options
    if args.get_info:
        selectors = sum([bool(args.by_id), bool(args.by_username), bool(args.by_invite)])
        if selectors == 0:
            print(f"{EMOJI['error']} --get-info requires one of: --by-id, --by-username, or --by-invite")
            exit(1)
        elif selectors > 1:
            print(f"{EMOJI['error']} --get-info can only use one selector at a time")
            exit(1)
    if any([args.by_id, args.by_username, args.by_invite]) and not args.get_info:
        print(f"{EMOJI['warning']} --by-id, --by-username, and --by-invite require --get-info")
    if not args.path and not args.get_info:
        print(f"{EMOJI['error']} The following arguments are required: --path")
        exit(2)

    # Write to file?
    if args.out_file:
        if Path(args.out_file).exists():
            print(f"\n{EMOJI['warning']} Output file already exists: {args.out_file}")
            response = input("Overwrite? (y/n): ").strip().lower()
            if response not in ['y', 'yes']:
                print(f"{EMOJI['error']} Script cancelled by user.")
                exit(1)
        try:
            global OUT_FILE
            OUT_FILE = open(args.out_file, 'w', encoding='UTF-8')
            print(f"{EMOJI['log']} Logging to: {args.out_file}")
        except Exception as e:
            OUT_FILE = None
            print(f"{EMOJI["error"]} Output file {args.out_file} cannot be created/accessed:\n{e}")
            exit(1)


def main():
    args = build_arg_parser().parse_args()

    # Validate args that only work with --get-identifiers
    validate_args(args)

    # Handle --get-info mode
    if args.get_info:
        client = connect_to_telegram(args.user)
        if not client:
            return
        try:
            print(
                get_entity_info(
                    client,
                    by_id=args.by_id,
                    by_username=args.by_username,
                    by_invite=args.by_invite
                )
            )
        finally:
            client.disconnect()
        return

    # Parse skip-time if provided
    skip_time_seconds = None
    if args.skip_time:
        try:
            skip_time_seconds = parse_time_expression(args.skip_time)
            hours = skip_time_seconds / 3600
            print(f"{EMOJI["time"]} Skip time: {skip_time_seconds}s ({hours:.1f} hours)")
        except ValueError as e:
            print(f"{EMOJI["error"]} Error: {e}")
            return

    # Parse skip statuses
    if args.skip:
        print(f"{EMOJI["skip"]} Skip statuses: {', '.join(args.skip)}")

    # Parse ignore statuses
    ignore_statuses = args.ignore if args.ignore else None
    if ignore_statuses:
        print(f"{EMOJI["ignored"]} Ignore statuses: {', '.join(ignore_statuses)}")

    # Parse no-skip-unknown
    if args.no_skip_unknown:
        print(f"{EMOJI["info"]} {EMOJI["file"]} with {EMOJI["unknown"]} status will be checked")

    # Find all .md files
    path = Path(args.path)
    if not path.exists():
        print(f"{EMOJI["error"]} Path does not exist: {path}")
        return

    md_files = list(path.glob('*.md'))

    if not md_files:
        print(f"{EMOJI["error"]} No .md files found in {path}")
        return

    print(f"{EMOJI["folder"]} {len(md_files)} .md files found")
    print(f"🔍 Filter: {args.type}")
    if args.dry_run:
        print(f"🔎 Mode: DRY-RUN (no file modifications)")
    print()

    # Connect to Telegram
    client = None
    if not (args.get_identifiers == 'all'):
        client = connect_to_telegram(args.user)

    # Handle --get-invites or --get-identifiers mode without connection if mode is 'all'
    if args.get_identifiers:
        list_identifiers(
            client,
            md_files,
            args
        )
        if client:
            client.disconnect()
        return

    full_check(client, args, ignore_statuses, md_files, skip_time_seconds)

    print(f"\n{EMOJI["info"]} Done!")


if __name__ == '__main__':
    main()
