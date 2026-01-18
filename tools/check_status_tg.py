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

def check_entity_status(client, identifier, is_invite=False):
    """
    Checks the status of a Telegram entity.

    Args:
        client: TelegramClient instance
        identifier (str): Username or invite hash
        is_invite (bool): Whether the identifier is an invite link

    Returns:
        tuple: (status, restriction_details) where:
            - status: 'active', 'banned', 'deleted', 'unknown', or 'error_<ExceptionName>'
            - restriction_details: dict with 'platform', 'reason', 'text' if banned, else None

    Status meanings:
        - 'active': Successfully retrieved and entity is accessible
        - 'banned': Confirmed banned by Telegram (restricted platform='all')
        - 'deleted': Confirmed deleted account (deleted=True, users only)
        - 'unknown': Cannot determine exact status (private, changed username,
                    invalid invite, no access, platform-specific restriction, etc.)
    """
    try:
        if is_invite:
            entity = client.get_entity(f'https://t.me/+{identifier}')
        else:
            entity = client.get_entity(identifier)

        # Successfully retrieved entity - now check its status

        # Check if user is deleted
        if hasattr(entity, 'deleted') and entity.deleted:
            return ('deleted', None)

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
                        return ('banned', details)

                # If we reach here, it's platform-specific restriction (not global ban)
                return ('unknown', None)
            else:
                # Restricted but no reason provided
                return ('unknown', None)

        return ('active', None)

    except ChannelPrivateError:
        # Channel/group is private or we don't have access
        return ('unknown', None)

    except (InviteHashExpiredError, InviteHashInvalidError):
        # Invite link is invalid/expired - doesn't mean the entity is banned
        return ('unknown', None)

    except (UsernameInvalidError, UsernameNotOccupiedError):
        # Username doesn't exist - could be changed, typo, or deleted
        return ('unknown', None)

    except ValueError as e:
        # Specific case: trying to access a channel/group we're not part of via invite link
        if "Cannot get entity from a channel" in str(e):
            return ('unknown', None)
        # Other ValueError cases (unexpected)
        print(f"    ⚠️  Unexpected ValueError: {str(e)}")
        return (f'error_ValueError', None)

    except FloodWaitError as e:
        print(f"⏸️  FloodWait: waiting {e.seconds}s...")
        time.sleep(e.seconds)
        return check_entity_status(client, identifier, is_invite)

    except Exception as e:
        print(f"    ⚠️  Unexpected error: {type(e).__name__}: {str(e)}")
        return (f'error_{type(e).__name__}', None)


# ============================================
# MARKDOWN FILE PARSING
# ============================================

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
    Extracts username OR invite link from markdown file.

    Args:
        content (str): Markdown file content

    Returns:
        tuple: (identifier, is_invite) where identifier is the username/hash and
               is_invite is a boolean indicating if it's an invite link
    """
    # Priority: username field (must start with @, otherwise it's likely a placeholder)
    username_match = re.search(r'username:\s*`?@([a-zA-Z0-9_]{5,32})`?', content)
    if username_match:
        return (username_match.group(1), False)

    # Fallback: invite link (active or expired)
    invite_match = re.search(r'invite:\s*(?:~~)?https://t\.me/\+([a-zA-Z0-9_-]+)', content)
    if invite_match:
        return (invite_match.group(1), True)

    return (None, None)


def get_last_status(content):
    """
    Extracts the most recent status entry from markdown content.
    Only returns a status if it has a valid date+time format.

    Args:
        content (str): Markdown file content

    Returns:
        tuple: (status, datetime) or (None, None) if no valid status found

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
        return (None, None)

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
            return (status, dt)
        except ValueError:
            # Date format is invalid - treat as no status
            return (None, None)

    # No valid status entry found (either no entry, or entry without valid date/time)
    return (None, None)


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
    last_status, last_datetime = get_last_status(content)

    if last_status is None:
        # No previous status, don't skip
        return (False, None)

    # Check if we should skip based on status
    if skip_statuses and last_status in skip_statuses:
        return (True, f"last status is '{last_status}'")

    # Check if we should skip based on time
    if skip_time_seconds is not None:
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

    Format:
    status:
    - `active`, `2026-01-19 14:32`

    Or with restriction details:
    status:
    - `banned`, `2026-01-19 14:32`
      - reason: `copyright violation`
      - text: `This content violates copyright...`

    Args:
        file_path (Path): Path to the markdown file
        new_status (str): New status to add
        restriction_details (dict): Optional dict with 'platform', 'reason', 'text'

    Returns:
        bool: True if successful, False otherwise
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    status_block_found = False
    status_block_line = -1

    # Find the status: block
    for i, line in enumerate(lines):
        if re.match(r'^status:\s*$', line.strip()):
            status_block_found = True
            status_block_line = i
            break

    if not status_block_found:
        print(f"    ⚠️  No 'status:' block found in {file_path.name}")
        return False

    # Create new status line(s)
    now = datetime.now()
    date_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%H:%M')

    new_status_lines = []
    new_status_lines.append(f"- `{new_status}`, `{date_str} {time_str}`\n")

    # Add restriction details if present
    if restriction_details:
        if 'reason' in restriction_details and restriction_details['reason']:
            new_status_lines.append(f"  - reason: `{restriction_details['reason']}`\n")
        if 'text' in restriction_details and restriction_details['text']:
            # Escape backticks in text to avoid breaking markdown
            text = restriction_details['text'].replace('`', "'")
            new_status_lines.append(f"  - text: `{text}`\n")

    # Reconstruct file
    new_lines = lines[:status_block_line + 1]
    new_lines.extend(new_status_lines)

    # Collect existing status entries (each entry can have multiple lines)
    existing_entries = []
    current_entry = []
    i = status_block_line + 1

    while i < len(lines):
        line = lines[i]

        # Check if this is a new status entry (starts with "- `")
        if re.match(r'^\s*-\s*`', line):
            # Save previous entry if exists
            if current_entry:
                existing_entries.append(current_entry)
            # Start new entry
            current_entry = [line]
        # Check if this is a sub-item (starts with "  - ")
        elif re.match(r'^\s{2,}-\s', line) and current_entry:
            # Part of current entry
            current_entry.append(line)
        else:
            # End of status block
            if current_entry:
                existing_entries.append(current_entry)
            # Add remaining lines
            new_lines.extend(lines[i:])
            break

        i += 1

    # If status block was at the end of file
    if current_entry and i >= len(lines):
        existing_entries.append(current_entry)

    # If we've reached the limit, remove the middle entry
    if len(existing_entries) >= MAX_STATUS_ENTRIES - 1:
        middle_index = len(existing_entries) // 2
        existing_entries.pop(middle_index)

    for entry in existing_entries:
        new_lines.extend(entry)

    # Write back
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
        print(f"   Create it with: echo '+213XXXXXXXXX' > {mobile_file}")
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

            # Extract identifier
            identifier, is_invite = extract_telegram_identifiers(content)
            if not identifier:
                print(f"⏭️  {md_file.name}: No identifier found")
                stats['skipped'] += 1
                stats['skipped_no_identifier'] += 1
                continue

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

            # Check status
            display_id = f"+{identifier[:15]}..." if is_invite else f"@{identifier}"
            print(f"⏳ {md_file.name}: {display_id}...", end=' ', flush=True)

            status, restriction_details = check_entity_status(client, identifier, is_invite)
            stats['total'] += 1

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
            elif status == 'unknown':
                stats['unknown'] += 1
                emoji = "❓"
            else:
                stats['error'] += 1
                emoji = "❌"

            print(f"{emoji} {status}")

            # Print restriction details if present
            if restriction_details:
                if 'reason' in restriction_details:
                    print(f"    📋 Reason: {restriction_details['reason']}")
                if 'text' in restriction_details:
                    text_preview = restriction_details['text'][:60] + '...' if len(
                        restriction_details['text']) > 60 else restriction_details['text']
                    print(f"    💬 Text: {text_preview}")

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

            # Update .md file (only if NOT dry-run)
            if not args.dry_run:
                if update_status_in_md(md_file, status, restriction_details):
                    print(f"    💾 File updated")
            else:
                # Show what WOULD be written
                date_str = now.strftime('%Y-%m-%d')
                time_str = now.strftime('%H:%M')
                print(f"    🔍 Would add: - `{status}`, `{date_str} {time_str}`")
                if restriction_details:
                    if 'reason' in restriction_details:
                        print(f"               - reason: `{restriction_details['reason']}`")
                    if 'text' in restriction_details:
                        print(f"               - text: `{restriction_details['text'][:50]}...`")

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
    print(f"❓ Unknown :     {stats['unknown']}")
    print(f"❌ Errors:      {stats['error']}")
    print()
    print(f"⏭️ Skipped (total):       {stats['skipped']}")
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

    print("\n✅ Done!")


if __name__ == '__main__':
    main()
