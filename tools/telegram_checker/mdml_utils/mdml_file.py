from telegram_checker.config.constants import (
    REGEX_ID,
    EMOJI,
    REGEX_NEXT_FIELD,
    REGEX_STATUS_BLOCK_PATTERN,
    REGEX_STATUS_SUB_ITEM,
    MAX_STATUS_ENTRIES,
    REGEX_STATUS_BLOCK_START
)
from telegram_checker.utils.helpers import (
    get_date_time,
    cut_text
)
from telegram_checker.utils.logger import get_logger
LOG = get_logger()


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
        LOG.output(f"  {EMOJI["warning"]} No 'status:' block found in {file_path.name}")
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
        LOG.output(f"  {EMOJI["id_mismatch"]} Expected ID: {expected_id}, found ID: {actual_id}")

    if last_status is not None and last_status != status:
        LOG.output(f"  {EMOJI["change"]} STATUS CHANGE: {last_status} → {status}")

    if restriction_details:
        if 'reason' in restriction_details:
            LOG.output(f"  {EMOJI["reason"]} Reason: {restriction_details['reason']}")
        if 'text' in restriction_details:
            text_preview = cut_text(restriction_details['text'], 120-11)
            LOG.output(f"  {EMOJI["text"]} Text: {text_preview}")

    # Handle file updates
    should_track_change = False
    was_updated = False

    if should_ignore:
        LOG.output(f"  {EMOJI["ignored"]} Ignoring status '{status}' (not updating file)")
    else:
        # Track status change
        if last_status != status:
            should_track_change = True

        # Update file
        if not is_dry_run:
            if update_status_in_md(md_file, status, restriction_details):
                LOG.output(f"  {EMOJI["saved"]} File updated")
                was_updated = True
        else:
            # Show what WOULD be written
            LOG.output(f"  {EMOJI["dry-run"]} Would add:")
            LOG.output(f"    `{status}`, `{get_date_time()}`")
            if restriction_details:
                if 'reason' in restriction_details:
                    LOG.output(f"    - reason: `{restriction_details['reason']}`")
                if 'text' in restriction_details:
                    LOG.output(f"    - text: `{restriction_details['text'][:50]}...`")

    return should_track_change, was_updated
