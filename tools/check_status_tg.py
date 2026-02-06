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

UI_HORIZONTAL_LINE = f"\n{60 * "-"}\n"

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
    print('---DEBUG---')
    print(f'{type(e).__name__}')
    print(f'{str(e)}')
    print('-----------')


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
        is_invite (bool): Whether the identifier is an invite link
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

        # If no identifier to fallback to, return unknown
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
    print(UI_HORIZONTAL_LINE)

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

    print("\n" + UI_HORIZONTAL_LINE)
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
        required=True,
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
        '--get-invites',
        nargs='?',
        const='all',
        choices=['all', 'valid'],
        help='Get list of invites (all = non-strikethrough, valid = tested with UserID)'
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
        '--tasks',
        action='store_true',
        help="With --get-invites: print results as markdown tasks"
    )
    parser.add_argument(
        '--valid-only',
        action='store_true',
        help="With --get-invites: only print valid invites"
    )
    return parser


def print_stats(stats):
    print("\n" + UI_HORIZONTAL_LINE)
    print(f"{EMOJI["stats"]} RESULTS")
    print(UI_HORIZONTAL_LINE)
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
    print("\n" + "!" * 60)
    print(f"{EMOJI["warning"]} FILES WITHOUT 'status:' BLOCK (STATUS DETECTED)")
    print(UI_HORIZONTAL_LINE)
    for item in no_status_block_results:
        print(f"• \\[[{item['file']}\\]] → {item['emoji']} {item['status']}")
    print(UI_HORIZONTAL_LINE)


def print_status_changed_files(status_changed_files):
    print("\n" + "!" * 60)
    print(f"{EMOJI["change"]} FILES WITH STATUS CHANGE (RENAME IN OBSIDIAN)")
    print(UI_HORIZONTAL_LINE)
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
    print(UI_HORIZONTAL_LINE)

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

    print(UI_HORIZONTAL_LINE)
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
    print(UI_HORIZONTAL_LINE)

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

    print(UI_HORIZONTAL_LINE)
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


def format_display_id(expected_id, identifiers, is_invite, method_used):
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
    display_id = format_display_id(expected_id, identifiers, is_invite, method_used)

    return status, restriction_details, actual_id, actual_username, method_used, display_id


def process_and_update_file(md_file, status, restriction_details, actual_id, expected_id, last_status, has_status_block, should_ignore, is_dry_run):
    """
    Displays additional info, updates file if needed, and prepares result data.

    Args:
        md_file: Path to markdown file
        status: Current status
        restriction_details: Restriction details (if any)
        actual_id: Actual entity ID (for id_mismatch)
        expected_id: Expected entity ID
        last_status: Previous status
        has_status_block: Whether file has status block
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


def print_invites(invites_list, is_check_list=True, valid_only=False):
    if not invites_list:
        return

    md_check_list = ''
    if is_check_list:
        md_check_list = '- [ ] '

    # Print results
    if len(invites_list) > 1:
        print(f"\n{EMOJI['invite']} Found {len(invites_list)} invite(s):\n")

    for inv in invites_list:
        if inv['valid'] is True:
            print(f"{md_check_list}{EMOJI["active"]} {inv['full_link']}")
            if inv['user_id']:
                print(f"  {EMOJI["id"]      } {inv['user_id']}")
            print(f"  {EMOJI["file"]    } {inv['file']}")
            print()
        elif inv['valid'] is False and not valid_only:
            print(f"{md_check_list}{EMOJI["no_emoji"]} {inv['full_link']}")
            print(f"  {EMOJI["file"]    } {inv['file']}")
            print(f"  {EMOJI["text"]    } {inv['reason']}")
            print(f"  {EMOJI["text"]    } {inv['message']}")
            print()
        else:  # valid is None, because we haven't checked for validity
            print(f"{md_check_list}{inv['full_link']}")
            print(f"  {EMOJI["file"]    } {inv['file']}")
            print()


def validate_invite(client, invite_hash):
    """
    Validates an invite link by checking the invite info.
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
        print(f"  {EMOJI['pause']} FloodWait: waiting {e.seconds}s...")
        time.sleep(e.seconds)
        return validate_invite(client, invite_hash)

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
        print(f"    echo '+XXXXXXXXXXX' > {mobile_file}")
        return

    phone = mobile_file.read_text(encoding='utf-8').strip()

    # Connect to Telegram
    session_file = session_dir / user
    print(f"{EMOJI["connecting"]} Connecting to Telegram (user: {user})...")
    client = TelegramClient(str(session_file), API_ID, API_HASH)
    client.start(phone=phone)
    print(f"{EMOJI["success"]} Connected!\n")
    return client


def main():
    args = build_arg_parser().parse_args()

    # Validate --no-skip usage
    if args.no_skip and not args.get_invites:
        print(f"{EMOJI['warning']} --no-skip can only be used with --get-invites")

    if args.continuous and not args.get_invites:
        print(f"{EMOJI['warning']} --continuous can only be used with --get-invites")

    if args.tasks and not args.get_invites:
        print(f"{EMOJI['warning']} --tasks can only be used with --get-invites")

    if args.valid_only and not args.get_invites:
        print(f"{EMOJI['warning']} --valid-only can only be used with --get-invites")

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
    skip_statuses = args.skip if args.skip else None
    if skip_statuses:
        print(f"{EMOJI["skip"]} Skip statuses: {', '.join(skip_statuses)}")

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

    # Handle --get-invites mode without connection if mode is 'all'
    if args.get_invites == 'all':
        invites_list = []

        for md_file in md_files:
            try:
                entity = TelegramEntity.from_file(md_file)

                # Skip files with banned/unknown status unless --no-skip
                if not args.no_skip:
                    last_status, _, _ = get_last_status(entity)
                    if last_status in ['banned', 'unknown']:
                        continue

                invites = entity.get_invites().active()

                for invite in invites:
                    invite_entry = {
                        'file': md_file.name,
                        'hash': invite.hash,
                        'full_link': f'https://t.me/+{invite.hash}',
                        'valid': None,
                        'reason': None,
                        'message': "Not validated"
                    }
                    if args.continuous:
                        print_invites([invite_entry], args.tasks, args.valid_only)
                    else:
                        invites_list.append(invite_entry)

            except Exception as e:
                print_debug(e)
                continue

        # Print results and exit (no Telegram connection needed)
        print_invites(invites_list, args.tasks, args.valid_only)
        return

    # Statistics
    stats = STATS_INIT.copy()

    # Connect to Telegram
    client = connect_to_telegram(args.user)

    # Handle --get-invites valid mode (requires connection)
    if args.get_invites == 'valid':
        invites_list = []

        for md_file in md_files:
            try:
                entity = TelegramEntity.from_file(md_file)

                # Skip files with banned/unknown status unless --no-skip
                if not args.no_skip:
                    last_status, _, _ = get_last_status(entity)
                    if last_status in ['banned', 'unknown']:
                        continue

                invites = entity.get_invites().active()

                for invite in invites:
                    # Build base invite entry
                    invite_entry = {
                        'file': md_file.name,
                        'hash': invite.hash,
                        'full_link': f'https://t.me/+{invite.hash}',
                    }
                    # Validate invite
                    (
                        invite_entry['valid'],
                        invite_entry['user_id'],
                        invite_entry['reason'],
                        invite_entry['message']
                    ) = validate_invite(client, invite.hash)

                    time.sleep(SLEEP_BETWEEN_CHECKS)  # Rate limiting
                    if args.continuous:
                        print_invites([invite_entry], args.tasks, args.valid_only)
                    else:
                        invites_list.append(invite_entry)

            except Exception as e:
                print_debug(e)
                continue

        # Print results
        print_invites(invites_list, args.tasks, args.valid_only)
        client.disconnect()
        return

    # Connect to Telegram (needed for normal checks)
    client = connect_to_telegram(args.user)

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
                should_skip, skip_reason = should_skip_entity(entity, skip_time_seconds, skip_statuses, not args.no_skip_unknown)
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
                        print(f"  ✨ Username discovered: @{actual_username}")
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
                    expected_id, last_status, has_status_block,
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

    print(f"\n{EMOJI["info"]} Done!")


if __name__ == '__main__':
    main()
