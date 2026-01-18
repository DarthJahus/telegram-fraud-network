#!/usr/bin/env python3
"""
Telegram Entities Status Checker
Checks the status of Telegram entities (channels, groups, users, bots) and updates markdown files.

Usage:
  python check_status_tg.py --path . --type all [--dry-run]
  python check_status_tg.py --path . --skip-time 86400 --skip unknown banned
  python check_status_tg.py --path . --skip-time "24*60*60"
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
# REMOVED: PHONE is now loaded per-user in main()

SLEEP_BETWEEN_CHECKS = 20  # seconds between each check
MAX_STATUS_ENTRIES = 10  # maximum number of status entries to keep


# ============================================
# ENTITY STATUS CHECKING
# ============================================

def check_entity_status(client, identifier, is_invite=False, expected_id=None):
    """
    Checks the status of a Telegram entity.

    Args:
        client: TelegramClient instance
        identifier (str): Username or invite hash
        is_invite (bool): Whether the identifier is an invite link
        expected_id (int, optional): Expected entity ID for verification

    Returns:
        tuple: (status, restriction_details, actual_id) where:
            - status: 'active', 'banned', 'deleted', 'id_mismatch', 'unknown', or 'error_<ExceptionName>'
            - restriction_details: dict with 'platform', 'reason', 'text' if banned, else None
            - actual_id: the actual entity ID (for id_mismatch cases), else None

    Status meanings:
        - 'active': Successfully retrieved and entity is accessible
        - 'banned': Confirmed banned by Telegram (restricted platform='all')
        - 'deleted': Confirmed deleted account (deleted=True, users only)
        - 'id_mismatch': Username/invite exists but ID doesn't match (username reused)
        - 'unknown': Cannot determine exact status (private, changed username,
                    invalid invite, no access, platform-specific restriction, etc.)
    """
    try:
        if is_invite:
            entity = client.get_entity(f'https://t.me/+{identifier}')
        else:
            entity = client.get_entity(identifier)

        # *** SAFEGUARD: Verify ID if expected_id is provided ***
        if expected_id is not None and hasattr(entity, 'id'):
            if entity.id != expected_id:
                # This is a DIFFERENT entity with the same username/invite!
                return ('id_mismatch', None, entity.id)

        # Successfully retrieved entity - now check its status

        # Check if user is deleted
        if hasattr(entity, 'deleted') and entity.deleted:
            return ('deleted', None, None)

        # Check if entity is restricted (banned by Telegram)
        if hasattr(entity, 'restricted') and entity.restricted:
            # Check restriction_reason to determine if it's a platform-wide ban
            if hasattr(entity, 'restriction_reason') and entity.restriction_reason:
                # restriction_reason is a list of RestrictionReason objects
                for restriction in entity.restriction_reason:
                    # Check if it's restricted for all platforms (ToS violation)
                    if restriction.platform == 'all':
                        # Extract restriction details
                        details = {
                            'platform': restriction.platform,
                            'reason': restriction.reason,
                            'text': restriction.text
                        }
                        return ('banned', details, None)

                # If we reach here, it's platform-specific restriction (not global ban)
                return ('unknown', None, None)
            else:
                # Restricted but no reason provided
                return ('unknown', None, None)

        return ('active', None, None)

    except ChannelPrivateError:
        # Channel/group is private or we don't have access
        return ('unknown', None, None)

    except (InviteHashExpiredError, InviteHashInvalidError):
        # Invite link is invalid/expired - doesn't mean the entity is banned
        return ('unknown', None, None)

    except (UsernameInvalidError, UsernameNotOccupiedError):
        # Username doesn't exist - could be changed, typo, or deleted
        return ('unknown', None, None)

    except ValueError as e:
        # Specific case: trying to access a channel/group we're not part of via invite link
        if "Cannot get entity from a channel" in str(e):
            return ('unknown', None, None)
        # Other ValueError cases (unexpected)
        print(f"  ⚠️ Unexpected ValueError: {str(e)}")
        return (f'unknown', None, None)

    except FloodWaitError as e:
        print(f"⏸️  FloodWait: waiting {e.seconds}s...")
        time.sleep(e.seconds)
        return check_entity_status(client, identifier, is_invite, expected_id)

    except Exception as e:
        print(f"  ⚠️ Unexpected error: {type(e).__name__}: {str(e)}")
        return (f'error_{type(e).__name__}', None, None)


# ============================================
# MARKDOWN FILE PARSING
# ============================================

def extract_entity_id(content):
    """Extract the entity ID from markdown content."""
    match = re.search(r'^id:\s*`?(\d+)`?', content, re.MULTILINE)
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
    match = re.search(r'^type:\s*(\w+)', content, re.MULTILINE)
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
    username_match = re.search(r'username:\s*`?@([a-zA-Z0-9_]{5,32})`?', content)
    if username_match:
        return (username_match.group(1), False)

    # Fallback 1: single invite link (inline format)
    # Format: invite: https://t.me/+HASH
    invite_single_match = re.search(r'^invite:\s*(?:~~)?https://t\.me/\+([a-zA-Z0-9_-]+)', content, re.MULTILINE)
    if invite_single_match:
        return ([invite_single_match.group(1)], True)

    # Fallback 2: invite list format
    # Format:
    # invite:
    # - https://t.me/+HASH1
    # - https://t.me/+HASH2
    invite_block_match = re.search(r'^invite:\s*$', content, re.MULTILINE)
    if invite_block_match:
        # Find the next field (end of invite block)
        next_field_match = re.search(r'^[a-z_]+:\s', content[invite_block_match.end():], re.MULTILINE)

        if next_field_match:
            # Extract only the invite block content
            invite_block = content[invite_block_match.end():invite_block_match.end() + next_field_match.start()]
        else:
            # Invite block goes to end of file
            invite_block = content[invite_block_match.end():]

        # Extract all invite hashes from the block only
        invite_hashes = re.findall(r'-\s*(?:~~)?https://t\.me/\+([a-zA-Z0-9_-]+)', invite_block)
        if invite_hashes:
            return (invite_hashes, True)

    return (None, None)


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
    status_match = re.search(r'^status:\s*$', content, re.MULTILINE)
    if not status_match:
        return (None, None, False)

    # Find the first status entry after "status:"
    # Pattern: - `<status>`, `<date> <time>`
    # This pattern REQUIRES both date and time to be present
    pattern = r'^\s*-\s*`([^`]+)`\s*,\s*`(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})`'

    # Search from the status: line onwards
    remaining_content = content[status_match.end():]
    match = re.search(pattern, remaining_content, re.MULTILINE)

    if match:
        status = match.group(1)
        date_str = match.group(2)
        time_str = match.group(3)

        try:
            dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            return (status, dt, True)
        except ValueError:
            # Date format is invalid - treat as no status
            return (None, None, True)

    # No valid status entry found (either no entry, or entry without valid date/time)
    return (None, None, True)


def should_skip_entity(content, skip_time_seconds, skip_statuses):
    """
    Determines if an entity should be skipped based on its last status.

    Args:
        content (str): Markdown file content
        skip_time_seconds (int or None): Skip if checked within this many seconds
        skip_statuses (list or None): Skip if last status is in this list

    Returns:
        tuple: (should_skip, reason) where reason explains why it was skipped
    """
    last_status, last_datetime, has_status_block = get_last_status(content)

    if last_status is None:
        # No previous status, don't skip
        return (False, None)

    # Check if we should skip based on status
    if skip_statuses and last_status in skip_statuses:
        return (True, f"last status is '{last_status}' (exception)")

    # Check if we should skip based on time
    # IMPORTANT: Never skip 'unknown' status based on time (always re-check)
    if skip_time_seconds is not None and last_status != 'unknown':
        time_since_check = datetime.now() - last_datetime
        if time_since_check.total_seconds() < skip_time_seconds:
            hours = int(time_since_check.total_seconds() / 3600)
            mins = int((time_since_check.total_seconds() % 3600) / 60)
            return (True, f"checked {hours}h {mins}m ago (status: {last_status})")

    return (False, None)

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
        if re.match(r'^status:\s*$', line.strip()):
            status_line_idx = i
            break

    if status_line_idx is None:
        print(f"  ⚠️  No 'status:' block found in {file_path.name}")
        return False

    # 2. Find the next field (end of status block)
    next_field_idx = None
    for i in range(status_line_idx + 1, len(lines)):
        # Next field starts with word characters followed by ':'
        if re.match(r'^[a-z_]+:\s', lines[i]):
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
        if re.match(r'^\s*-\s*`[^`]+`,\s*`\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}`', line):
            # Save previous entry if exists
            if current_entry:
                existing_entries.append(current_entry)
            # Start new entry
            current_entry = [line]
        # Check if this is a sub-item (part of current entry)
        elif re.match(r'^\s{2,}-\s', line) and current_entry:
            current_entry.append(line)
        # Else: ignore malformed lines

    # Don't forget the last entry
    if current_entry:
        existing_entries.append(current_entry)

    # 4. Create new status entry
    now = datetime.now()
    date_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%H:%M')

    new_entry = [f"- `{new_status}`, `{date_str} {time_str}`\n"]

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
    print("🔍 DRY-RUN SUMMARY - Changes to apply:")
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
        print(f"\n❌ ERRORS ({len(errors)}):")
        for r in errors:
            print(f"  • {r['file']}: {r['identifier']} → {r['status']}")

    print("\n" + "=" * 60)
    print("ℹ️  To apply these changes, run again without --dry-run")
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

def main():
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

    args = parser.parse_args()

    # Parse skip-time if provided
    skip_time_seconds = None
    if args.skip_time:
        try:
            skip_time_seconds = parse_time_expression(args.skip_time)
            hours = skip_time_seconds / 3600
            print(f"⏰ Skip time: {skip_time_seconds}s ({hours:.1f} hours)")
        except ValueError as e:
            print(f"❌ Error: {e}")
            return

    # Parse skip statuses
    skip_statuses = args.skip if args.skip else None
    if skip_statuses:
        print(f"🚫 Skip statuses: {', '.join(skip_statuses)}")

    # Find all .md files
    path = Path(args.path)
    if not path.exists():
        print(f"❌ Path does not exist: {path}")
        return

    md_files = list(path.glob('*.md'))

    if not md_files:
        print(f"❌ No .md files found in {path}")
        return

    print(f"📂 {len(md_files)} .md files found")
    print(f"🔍 Filter: {args.type}")
    if args.dry_run:
        print(f"🔍 Mode: DRY-RUN (no file modifications)")
    print()

    # Load phone number for this user
    session_dir = Path('.secret')
    session_dir.mkdir(exist_ok=True)
    mobile_file = session_dir / f'{args.user}.mobile'

    if not mobile_file.exists():
        print(f"❌ Mobile file not found: {mobile_file}")
        print(f"   Create it with: echo '+XXXXXXXXXXX' > {mobile_file}")
        return

    phone = mobile_file.read_text(encoding='utf-8').strip()

    # Connect to Telegram
    session_file = session_dir / args.user
    print(f"📡 Connecting to Telegram (user: {args.user})...")
    client = TelegramClient(str(session_file), API_ID, API_HASH)
    client.start(phone=phone)
    print("✅ Connected!\n")

    # Statistics
    stats = {
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
        'error': 0
    }

    # Store results for dry-run summary
    results = []
    status_changed_files = []
    no_status_block_results = []

    try:
        for md_file in md_files:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Check type filter
            entity_type = get_entity_type_from_md(content)
            if args.type != 'all' and entity_type != args.type:
                stats['skipped'] += 1
                stats['skipped_type'] += 1
                continue

            # Extract identifier and ID
            identifiers, is_invite = extract_telegram_identifiers(content)
            expected_id = extract_entity_id(content)
            if not identifiers:
                print(f"⏭️  {md_file.name}: No identifier found")
                stats['skipped'] += 1
                stats['skipped_no_identifier'] += 1
                continue

            last_status, last_datetime, has_status_block = get_last_status(content)

            # Check if we should skip based on last status
            should_skip, skip_reason = should_skip_entity(content, skip_time_seconds, skip_statuses)
            if should_skip:
                print(f"⏭️  {md_file.name}: Skipped ({skip_reason})")
                stats['skipped'] += 1
                if 'checked' in skip_reason and 'ago' in skip_reason:
                    stats['skipped_time'] += 1
                elif 'last status' in skip_reason:
                    stats['skipped_status'] += 1
                continue

            # Check status (handle both single username and multiple invites)
            if is_invite:
                # Multiple invites: try each until we find 'active'
                invite_list = identifiers if isinstance(identifiers, list) else [identifiers]
                print(f"⏳ {md_file.name}: {len(invite_list)} invite(s) to check...")

                status = None
                restriction_details = None
                actual_id = None

                for idx, invite_hash in enumerate(invite_list, 1):
                    display_id = f"+{invite_hash[:15]}..."
                    print(f"   [{idx}/{len(invite_list)}] {display_id}...", end=' ', flush=True)

                    status, restriction_details, actual_id = check_entity_status(
                        client, invite_hash, True, expected_id
                    )

                    # Show status
                    if status == 'active':
                        print(f"✅ active")
                        break  # Stop at first active invite
                    elif status == 'banned':
                        print(f"🔨 banned")
                        break  # Stop if banned (definitive)
                    elif status == 'deleted':
                        print(f"🗑️ deleted")
                        break  # Stop if deleted (definitive)
                    elif status == 'id_mismatch':
                        print(f"⚠️ id_mismatch")
                        break  # Stop if ID mismatch (definitive)
                    else:
                        print(f"❓ {status}")
                        # Continue to next invite

                    # Sleep between invite checks
                    if idx < len(invite_list):
                        time.sleep(5)  # Shorter delay between invites

                display_id = f"+{invite_list[0][:10]}... ({len(invite_list)} invite(s))"
            else:
                # Single username
                identifier = identifiers
                display_id = f"@{identifier}"
                print(f"⏳ {md_file.name}: {display_id}...", end=' ', flush=True)

                status, restriction_details, actual_id = check_entity_status(
                    client, identifier, False, expected_id
                )

            stats['total'] += 1

            # Detect status change
            if last_status != status:
                status_changed_files.append({
                    'file': md_file.name,
                    'old': last_status,
                    'new': status
                })

            # Update stats and get emoji
            if status == 'active':
                stats['active'] += 1
                emoji = "✅"
            elif status == 'banned':
                stats['banned'] += 1
                emoji = "🔨"
            elif status == 'deleted':
                stats['deleted'] += 1
                emoji = "🗑️"
            elif status == 'id_mismatch':
                stats['id_mismatch'] += 1
                emoji = "⚠️"
            elif status == 'unknown':
                stats['unknown'] += 1
                emoji = "❓"
            else:
                stats['error'] += 1
                emoji = "❌"

            if not is_invite:  # Only print status for username (already printed for invites)
                print(f"{emoji} {status}")

            # Show actual ID for id_mismatch
            if status == 'id_mismatch' and actual_id:
                print(f"  ⚠️  Expected ID: {expected_id}, found ID: {actual_id} ❕")

            if last_status is not None and last_status != status:
                print(f"  🔄 STATUS CHANGE: {last_status} → {status} ❕")

            # Print restriction details if present
            if restriction_details:
                if 'reason' in restriction_details:
                    print(f"  📋 Reason: {restriction_details['reason']}")
                if 'text' in restriction_details:
                    text_preview = restriction_details['text'][:60] + '...' if len(
                        restriction_details['text']) > 60 else restriction_details['text']
                    print(f"  💬 Text: {text_preview}")

            # Store result for dry-run summary
            now = datetime.now()
            result = {
                'file': md_file.name,
                'identifier': display_id,
                'status': status,
                'timestamp': now.strftime('%Y-%m-%d %H:%M'),
                'emoji': emoji,
                'restriction_details': restriction_details
            }
            results.append(result)

            if not has_status_block:
                no_status_block_results.append(result)

            # Update .md file (only if NOT dry-run)
            if not args.dry_run:
                if update_status_in_md(md_file, status, restriction_details):
                    print(f"  💾 File updated")
            else:
                # Show what WOULD be written
                date_str = now.strftime('%Y-%m-%d')
                time_str = now.strftime('%H:%M')
                print(f"  🔍 Would add: - `{status}`, `{date_str} {time_str}`")
                if restriction_details:
                    if 'reason' in restriction_details:
                        print(f"             - reason: `{restriction_details['reason']}`")
                    if 'text' in restriction_details:
                        print(f"             - text: `{restriction_details['text'][:50]}...`")

            # Sleep between checks to avoid rate limiting
            if md_file != md_files[-1]:  # Don't sleep after last file
                time.sleep(SLEEP_BETWEEN_CHECKS)

    finally:
        # Always disconnect, even if there's an error
        client.disconnect()

    # Final statistics
    print("\n" + "=" * 60)
    print("📊 RESULTS")
    print("=" * 60)
    print(f"Total checked:  {stats['total']}")
    print(f"✅ Active:      {stats['active']}")
    print(f"🔨 Banned:      {stats['banned']}")
    print(f"🗑️ Deleted:     {stats['deleted']}")
    print(f"⚠️ ID Mismatch: {stats['id_mismatch']}")
    print(f"❓ Unknown:     {stats['unknown']}")
    print(f"❌ Errors:      {stats['error']}")
    print()
    print(f"⏭️ Skipped (total):      {stats['skipped']}")
    if stats['skipped_time'] > 0:
        print(f"   └─ Recently checked:  {stats['skipped_time']}")
    if stats['skipped_status'] > 0:
        print(f"   └─ By status:         {stats['skipped_status']}")
    if stats['skipped_no_identifier'] > 0:
        print(f"   └─ No identifier:     {stats['skipped_no_identifier']}")
    if stats['skipped_type'] > 0:
        print(f"   └─ Wrong type:        {stats['skipped_type']}")
    print("=" * 60)

    # Dry-run summary
    if args.dry_run:
        print_dry_run_summary(results)

    if status_changed_files:
        print("\n" + "!" * 60)
        print("✏️ FILES WITH STATUS CHANGE (RENAME IN OBSIDIAN)")
        print("!" * 60)
        for item in status_changed_files:
            print(f"• {item['file']} : {item['old']} → {item['new']}")
        print("!" * 60)


    if no_status_block_results:
        print("\n" + "!" * 60)
        print("⚠️ FILES WITHOUT 'status:' BLOCK (STATUS DETECTED)")
        print("!" * 60)
        for r in no_status_block_results:
            print(f"• {r['file']} → {r['emoji']} {r['status']}")
        print("!" * 60)


    print("\n✅ Done!")


if __name__ == '__main__':
    main()
