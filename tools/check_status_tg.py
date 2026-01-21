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
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from telethon.sync import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    FloodWaitError
)

# ============================================
# CONFIGURATION
# ============================================
API_ID = int(open('.secret/api_id', 'r', encoding='utf-8').read().strip())
API_HASH = open('.secret/api_hash', 'r', encoding='utf-8').read().strip()
SLEEP_BETWEEN_CHECKS = 10  # seconds between each check
MAX_STATUS_ENTRIES = 10  # maximum number of status entries to keep

# ============================================
# REGEX
# ============================================

REGEX_ID = re.compile(pattern=r'^id:\s*`?(\d+)`?', flags=re.MULTILINE)
REGEX_TYPE = re.compile(pattern=r'^type:\s*(\w+)', flags=re.MULTILINE)
REGEX_USERNAME = re.compile(pattern=r'username:\s*`?@([a-zA-Z0-9_]{5,32})`?')

REGEX_INVITE_INLINE = re.compile(pattern=r'^invite:\s*(?:~~)?https://t\.me/\+([a-zA-Z0-9_-]+)', flags=re.MULTILINE)
REGEX_INVITE_BLOCK_START = re.compile(pattern=r'^invite:\s*$', flags=re.MULTILINE)
REGEX_INVITE_LINK = re.compile(pattern=r'-\s*(?:~~)?https://t\.me/\+([a-zA-Z0-9_-]+)')

REGEX_STATUS_BLOCK_START = re.compile(pattern=r'^status:\s*$', flags=re.MULTILINE)
REGEX_STATUS_ENTRY_FULL =  re.compile(pattern=r'^\s*-\s*`([^`]+)`\s*,\s*`(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})`', flags=re.MULTILINE)
REGEX_STATUS_BLOCK_PATTERN = re.compile(pattern=r'^\s*-\s*`[^`]+`,\s*`\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}`', flags=re.MULTILINE)
REGEX_STATUS_SUB_ITEM = re.compile(pattern=r'^\s{2,}-\s')

REGEX_NEXT_FIELD = re.compile(pattern=r'^[a-z_]+:\s', flags=re.MULTILINE)

# ============================================
# Variables & other constants
# ============================================

EMOJI = {
    'active':      "🔥",
    'banned':      "🔨",
    'deleted':     "🗑️",
    'id_mismatch': "⚠️",
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
    'warning':     "⚠️",
    'info':        "ℹ️",
    'saved':       "💾",
    'reason':      "📋",
    'text':        "💬",
    'methods':     "💊",
    'invite':      "⏳",
    'change':      "🔄",
    "pause":       "⏸️"
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


# ============================================
# Helper functions
# ============================================
def get_date_time(get_date=True, get_time=True):
    dt_format = ('%Y-%m-%d' if get_date else '') + (' %H:%M' if get_time else '')
    return datetime.now().strftime(dt_format).strip()


def cut_text(text, limit=120):
    if len(text) > limit:
        return text[:(limit-3)] + '...'
    return text


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
        return ('deleted', None)

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

    return ('active', None)


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
            return (status, restriction_details, None, 'id')
        # If ID fetch failed, continue to fallback methods below (if identifier provided)

        # If no identifier to fallback to, return unknown
        if identifier is None:
            return 'unknown', None, None, 'error'

    # If no expected_id AND no identifier, we have nothing to check
    if identifier is None:
        return 'unknown', None, None, 'error'

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
                return 'id_mismatch', None, entity.id, method

        # Successfully retrieved entity - now check its status
        status, restriction_details = analyze_entity_status(entity)
        method = 'invite' if is_invite else 'username'
        return status, restriction_details, None, method

    except ChannelPrivateError:
        # Channel exists, but we don't have access
        # For invites: if we can see the invite page, the channel is active
        # For usernames: the channel exists but is private
        return 'active', None, None, ('invite' if is_invite else 'username')

    except (InviteHashExpiredError, InviteHashInvalidError):
        # Invite is truly invalid/expired
        return 'unknown', None, None, 'error'

    except (UsernameInvalidError, UsernameNotOccupiedError):
        # Username doesn't exist or is invalid
        return 'unknown', None, None, 'error'

    except ValueError as e:
        if "Cannot get entity from a channel" in str(e):
            # This error specifically means the channel/group exists, but we're not a member
            # Different from expired/invalid invites (which raise InviteHash/Username errors)
            # Therefore, the entity is active, just not accessible to us
            return 'active', None, None, ('invite' if is_invite else 'username')
        # Other ValueError cases
        print(f"  {EMOJI["warning"]} Unexpected ValueError: {str(e)}")
        return 'unknown', None, None, 'error'

    except FloodWaitError as e:
        print(f"\n\n{EMOJI["pause"]} FloodWait: waiting {e.seconds}s...")
        time.sleep(e.seconds)
        return check_entity_status(client, identifier, is_invite, expected_id)

    except Exception as e:
        print(f"  {EMOJI["warning"]} Unexpected error: {type(e).__name__}: {str(e)}")
        return f'error_{type(e).__name__}', None, None, 'error'


# ============================================
# MARKDOWN FILE PARSING
# ============================================

def extract_entity_id(content):
    """Extract the entity ID from markdown content."""
    match = REGEX_ID.search(content)
    if match:
        return int(match.group(1))
    return None


def get_entity_type_from_md(content):
    """
    Detects the entity type from markdown content.

    Args:
        content (str): Markdown file content

    Returns:
        str or None: Entity type (channel, group, user, bot) or None if not found
    """
    match = REGEX_TYPE.search(content)
    if match:
        return match.group(1).lower()
    return None


def extract_telegram_identifiers(content):
    """
    Extracts username OR invite link(s) from markdown file.

    Args:
        content (str): Markdown file content

    Returns:
        tuple: (identifier, is_invite) where:
            - identifier: str (username) or list[str] (invite hashes)
            - is_invite: bool (False for username, True for invites)
    """
    # Priority: username field (must start with @, otherwise it's likely a placeholder)
    username_match = REGEX_USERNAME.search(content)
    if username_match:
        return username_match.group(1), False

    # Fallback 1: single invite link (inline format)
    # Format: invite: https://t.me/+HASH
    invite_single_match = REGEX_INVITE_INLINE.search(content)
    if invite_single_match:
        return [invite_single_match.group(1)], True

    # Fallback 2: invite list format
    # invite:
    # - https://t.me/+HASH1
    # - https://t.me/+HASH2
    invite_block_match = REGEX_INVITE_BLOCK_START.search(content)
    if invite_block_match:
        # Find the next field (end of invite block)
        next_field_match = REGEX_NEXT_FIELD.search(content[invite_block_match.end():])

        if next_field_match:
            # Extract only the invite block content
            invite_block = content[invite_block_match.end():invite_block_match.end() + next_field_match.start()]
        else:
            # Invite block goes to end of file
            invite_block = content[invite_block_match.end():]

        # Extract all invite hashes from the block only
        invite_hashes = REGEX_INVITE_LINK.findall(invite_block)
        if invite_hashes:
            return invite_hashes, True

    return None, None


def get_last_status(content):
    """
    Extracts the most recent status entry from markdown content.
    Only returns a status if it has a valid date+time format.

    Args:
        content (str): Markdown file content

    Returns:
        tuple: (status, datetime, has_status_block) or (None, None, has_status_block) if no valid status found

    Note: If a status entry exists but doesn't have a valid date/time,
          it is ignored (treated as if no status exists).

    Example valid status block:
        status:
        - `active`, `2026-01-18 14:32`
        - `unknown`, `2026-01-17 10:15`
    """
    # Find the status: block
    status_match = REGEX_STATUS_BLOCK_START.search(content)
    if not status_match:
        return None, None, False

    # Find the first status entry after "status:"
    # Pattern: - `<status>`, `<date> <time>`
    # This pattern REQUIRES both date and time to be present

    # Search from the status: line onwards
    remaining_content = content[status_match.end():]
    match = REGEX_STATUS_ENTRY_FULL.search(remaining_content)

    if match:
        status = match.group(1)
        date_str = match.group(2)
        time_str = match.group(3)

        try:
            dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            return status, dt, True
        except ValueError:
            # Date format is invalid - treat as no status
            return None, None, True

    # No valid status entry found (either no entry, or entry without valid date/time)
    return None, None, True


def should_skip_entity(content, skip_time_seconds, skip_statuses, skip_unknown=True):
    """
    Determines if an entity should be skipped based on its last status.

    Args:
        content (str): Markdown file content
        skip_time_seconds (int or None): Skip if checked within this many seconds
        skip_statuses (list or None): Skip if last status is in this list
        skip_unknown (default: True): Skip when last_stats is Unknown

    Returns:
        tuple: (should_skip, reason) where reason explains why it was skipped
    """
    last_status, last_datetime, has_status_block = get_last_status(content)

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

    print("\n" + "=" * 60)
    print(f"{EMOJI["dry-run"]} DRY-RUN SUMMARY - Changes to apply:")
    print("=" * 60)

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

    print("\n" + "=" * 60)
    print(f"{EMOJI["info"]} To apply these changes, run again without --dry-run")
    print("=" * 60)


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
    return parser


def print_stats(stats):
    print("\n" + "=" * 60)
    print(f"{EMOJI["stats"]} RESULTS")
    print("=" * 60)
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
    print("=" * 60)


def print_no_status_block(no_status_block_results):
    print("\n" + "!" * 60)
    print(f"{EMOJI["warning"]} FILES WITHOUT 'status:' BLOCK (STATUS DETECTED)")
    print("-" * 60)
    for r in no_status_block_results:
        print(f"• {r['file']} → {r['emoji']} {r['status']}")
    print("-" * 60)


def print_status_changed_files(status_changed_files):
    print("\n" + "!" * 60)
    print(f"{EMOJI["change"]} FILES WITH STATUS CHANGE (RENAME IN OBSIDIAN)")
    print("-" * 60)
    for item in status_changed_files:
        print(f"• {item['file']} : {item['old']} → {item['new']}")
    print("-" * 60)


def check_and_display(client, identifier, is_invite, expected_id, label, stats):
    """
    Helper function to check status and display result.

    Returns:
        tuple: (status, restriction_details, actual_id, method_used)
    """
    print(f"{label}...", end=' ', flush=True)
    status, restriction_details, actual_id, method_used = check_entity_status(
        client, identifier, is_invite, expected_id
    )

    if method_used in stats['method']:
        stats['method'][method_used] += 1

    emoji = EMOJI.get(status, EMOJI["no_emoji"])
    print(f"{emoji} {status}")

    return status, restriction_details, actual_id, method_used


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
        tuple: (status, restriction_details, actual_id, method_used, display_id)
    """
    status = None
    restriction_details = None
    actual_id = None
    method_used = None

    # PRIORITY 1: Try by ID first (most reliable)
    if expected_id:
        status, restriction_details, actual_id, method_used = check_and_display(
            client, None, False, expected_id,
            f"  {EMOJI.get("id")} Checking by ID: {expected_id}",
            stats
        )

    # PRIORITY 2: Fallback to invite links (if ID failed or no ID)
    if status is None or status == 'unknown':
        if is_invite and identifiers:
            invite_list = identifiers if isinstance(identifiers, list) else [identifiers]
            print(f"  {EMOJI["fallback"]} Fallback: Checking {len(invite_list)} invite(s)...")

            for idx, invite_hash in enumerate(invite_list, 1):
                status, restriction_details, actual_id, method_used = check_and_display(client, invite_hash, True, expected_id, f"    {EMOJI["invite"]} [{idx}/{len(invite_list)}] +{invite_hash}", stats)

                # Stop if we get a definitive answer
                if status != 'unknown':
                    break

                # Sleep between invite checks
                if idx < len(invite_list):
                    time.sleep(5)

    # PRIORITY 3: Fallback to username (last resort)
    if status is None or status == 'unknown':
        if not is_invite and identifiers:
            status, restriction_details, actual_id, method_used = check_and_display(client, identifiers, False, expected_id, f"  {EMOJI["handle"]} Fallback: Checking @{identifiers}", stats)

    # Final fallback (should rarely happen)
    if status is None:
        status = 'unknown'
        method_used = 'error'

    # Format display ID based on what succeeded
    display_id = format_display_id(expected_id, identifiers, is_invite, method_used)

    return status, restriction_details, actual_id, method_used, display_id


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


def main():
    args = build_arg_parser().parse_args()

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

    # Load phone number for this user
    session_dir = Path('.secret')
    session_dir.mkdir(exist_ok=True)
    mobile_file = session_dir / f'{args.user}.mobile'

    if not mobile_file.exists():
        print(f"{EMOJI["error"]} Mobile file not found: {mobile_file}")
        print(f"  Create it with:")
        print(f"    echo '+XXXXXXXXXXX' > {mobile_file}")
        return

    phone = mobile_file.read_text(encoding='utf-8').strip()

    # Connect to Telegram
    session_file = session_dir / args.user
    print(f"{EMOJI["connecting"]} Connecting to Telegram (user: {args.user})...")
    client = TelegramClient(str(session_file), API_ID, API_HASH)
    client.start(phone=phone)
    print(f"{EMOJI["success"]} Connected!")

    # Statistics
    stats = STATS_INIT.copy()

    # Store results for dry-run summary
    results = []
    status_changed_files = []
    no_status_block_results = []

    try:
        for md_file in md_files:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()

            print()
            print(f"{EMOJI["file"]} {md_file.name}")

            # Check type filter
            entity_type = get_entity_type_from_md(content)
            if args.type != 'all' and entity_type != args.type:
                stats['skipped'] += 1
                stats['skipped_type'] += 1
                continue

            # Extract ALL identifiers upfront
            expected_id = extract_entity_id(content)
            identifiers, is_invite = extract_telegram_identifiers(content)

            # If no ID AND no identifiers, skip entirely
            if not expected_id and not identifiers:
                print(f"   Skipped: No identifier found")
                stats['skipped'] += 1
                stats['skipped_no_identifier'] += 1
                continue

            # Get last status info
            last_status, last_datetime, has_status_block = get_last_status(content)

            # Check if we should skip based on last status
            should_skip, skip_reason = should_skip_entity(content, skip_time_seconds, skip_statuses, not args.no_skip_unknown)
            if should_skip:
                print(f"  {EMOJI["skip"]} Skipped: ({skip_reason})")
                stats['skipped'] += 1
                if 'checked' in skip_reason and 'ago' in skip_reason:
                    stats['skipped_time'] += 1
                elif 'last status' in skip_reason:
                    stats['skipped_status'] += 1
                continue

            # Check entity status with priority fallback
            status, restriction_details, actual_id, method_used, display_id = check_entity_with_fallback(
                client, expected_id, identifiers, is_invite, stats
            )

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

    print(f"\n{EMOJI["info"]} Done!")


if __name__ == '__main__':
    main()
