import re
import sys
from pathlib import Path


def has_frontmatter(content):
    """Check if the file already has frontmatter"""
    return content.strip().startswith('---')


def split_frontmatter(content):
    """Separate frontmatter from the rest of the content

    Returns:
        tuple: (frontmatter_text, body_content, has_fm)
    """
    if content.strip().startswith('---'):
        match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', content, re.DOTALL)
        if match:
            return match.group(1), match.group(2), True
    return '', content, False


def extract_metadata(content, keys):
    """Extract specified metadata from content (excluding frontmatter)"""
    metadata = {}

    # Separate frontmatter from body
    _, body, _ = split_frontmatter(content)

    for key in keys:
        # Flexible pattern: key: value (with or without backticks)
        pattern = rf'^{re.escape(key)}:\s*`?([^`\n]+?)`?\s*$'
        match = re.search(pattern, body, re.MULTILINE)

        if match:
            value = match.group(1).strip()
            metadata[key] = value

    return metadata


def remove_inline_metadata(content, keys):
    """Remove inline metadata lines from content (excluding frontmatter)"""
    # Separate frontmatter and body
    fm_text, body, has_fm = split_frontmatter(content)

    lines = body.split('\n')
    new_lines = []

    for line in lines:
        # Check if the line starts with one of the keys we're looking for
        should_remove = False
        for key in keys:
            if line.strip().startswith(f'{key}:'):
                should_remove = True
                break

        if not should_remove:
            new_lines.append(line)

    cleaned_body = '\n'.join(new_lines)

    # Rebuild with frontmatter if present
    if has_fm:
        return f'---\n{fm_text}\n---\n{cleaned_body}'
    else:
        return cleaned_body


def parse_simple_yaml(yaml_text):
    """Parse simple YAML: one key per line, format 'key: value'"""
    result = {}

    for line in yaml_text.split('\n'):
        line = line.strip()
        if not line:
            continue

        if ':' in line:
            parts = line.split(':', 1)
            key = parts[0].strip()
            value = parts[1].strip() if len(parts) > 1 else ''
            result[key] = value

    return result


def add_frontmatter(content, metadata, resolutions=None):
    """Add or update frontmatter. Returns (new_content, conflicts)"""
    conflicts = {}

    if has_frontmatter(content):
        # Extract existing frontmatter
        match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', content, re.DOTALL)
        if match:
            existing_yaml_text = match.group(1)
            rest_content = match.group(2)

            # Parse existing YAML
            yaml_dict = parse_simple_yaml(existing_yaml_text)

            # Process each key from extracted metadata
            for key, new_value in metadata.items():
                if key in yaml_dict:
                    existing_value = yaml_dict[key]

                    # Compare values
                    if existing_value != new_value:
                        if resolutions and key in resolutions:
                            # Apply resolution
                            if resolutions[key] == 'content':
                                yaml_dict[key] = new_value
                            # If 'yaml', keep existing_value (do nothing)
                        else:
                            # Conflict to resolve
                            conflicts[key] = {'yaml': existing_value, 'content': new_value}
                    # Otherwise, identical values: do nothing
                else:
                    # Key doesn't exist in YAML: add it
                    yaml_dict[key] = new_value

            # Rebuild YAML (simple: one line per key)
            yaml_lines = [f'{k}: {v}' for k, v in yaml_dict.items()]
            new_yaml = '\n'.join(yaml_lines)

            return f'---\n{new_yaml}\n---\n{rest_content}', conflicts
    else:
        # No frontmatter: create a new one
        yaml_lines = [f'{k}: {v}' for k, v in metadata.items()]
        yaml_content = '\n'.join(yaml_lines)
        return f'---\n{yaml_content}\n---\n\n{content}', conflicts

    return content, conflicts


def resolve_conflicts(filepath, conflicts, global_choice=None):
    """Ask user how to resolve conflicts

    Returns:
        tuple: (resolutions dict, new_global_choice)
    """
    if global_choice == 'overwrite_all':
        return {key: 'content' for key in conflicts.keys()}, global_choice

    if global_choice == 'ignore_all':
        return None, global_choice

    print(f"\n⚠️  CONFLICT detected in: {filepath}")

    resolutions = {}
    for key, values in conflicts.items():
        print(f"\n  Key: {key}")
        print(f"    [O] Overwrite (keep content value): '{values['content']}'")
        print(f"    [I] Ignore    (keep YAML value):    '{values['yaml']}'")
        print(f"    [Y] Overwrite ALL (all following conflicts)")
        print(f"    [N] Ignore ALL (all following conflicts)")
        print(f"    [S] Skip this file")

        while True:
            choice = input(f"  Your choice for '{key}' [O/I/Y/N/S]: ").strip().upper()

            if choice == 'O':
                resolutions[key] = 'content'
                break
            elif choice == 'I':
                resolutions[key] = 'yaml'
                break
            elif choice == 'Y':
                resolutions[key] = 'content'
                for remaining_key in conflicts.keys():
                    if remaining_key not in resolutions:
                        resolutions[remaining_key] = 'content'
                return resolutions, 'overwrite_all'
            elif choice == 'N':
                return None, 'ignore_all'
            elif choice == 'S':
                return None, global_choice
            else:
                print("  Invalid choice. Enter O, I, Y, N or S.")

    return resolutions, global_choice


def process_file(filepath, keys, dry_run=True, interactive=True, global_choice=None):
    """Process a markdown file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Extract metadata from content
        metadata = extract_metadata(content, keys)

        if not metadata:
            return None, global_choice

        # Clean content
        cleaned_content = remove_inline_metadata(content, keys)

        # Add/update frontmatter
        new_content, conflicts = add_frontmatter(cleaned_content, metadata)

        if conflicts:
            if interactive and not dry_run:
                resolutions, new_global_choice = resolve_conflicts(filepath, conflicts, global_choice)

                if resolutions is None:
                    print(f"  → File skipped\n")
                    return {'metadata': metadata, 'conflicts': conflicts, 'skipped': True}, new_global_choice

                # Reapply with resolutions
                new_content, _ = add_frontmatter(cleaned_content, metadata, resolutions)

                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"  ✓ Conflicts resolved and file converted\n")
                return {'metadata': metadata, 'conflicts': conflicts, 'resolved': True}, new_global_choice
            else:
                # Dry-run or non-interactive mode
                print(f"⚠️  [CONFLICT] {filepath}")
                for key, values in conflicts.items():
                    print(f"    {key}:")
                    print(f"      YAML:    '{values['yaml']}'")
                    print(f"      Content: '{values['content']}'")
                return {'metadata': metadata, 'conflicts': conflicts, 'skipped': True}, global_choice

        if dry_run:
            print(f"✓ [DRY RUN] {filepath}")
            print(f"  Metadata: {metadata}")
            return {'metadata': metadata, 'conflicts': None}, global_choice
        else:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"✓ [CONVERTED] {filepath}")
            return {'metadata': metadata, 'conflicts': None}, global_choice

    except Exception as e:
        print(f"❌ [ERROR] {filepath}: {e}")
        return None, global_choice


def process_vault(vault_path, keys, dry_run=True, interactive=True):
    """Process all .md files in the vault"""
    vault = Path(vault_path)

    if not vault.exists():
        print(f"❌ [ERROR] Path '{vault_path}' does not exist")
        return

    md_files = list(vault.rglob('*.md'))

    print(f"{'=' * 60}")
    print(f"Mode: {'DRY RUN (simulation)' if dry_run else 'ACTUAL CONVERSION'}")
    print(f"Keys searched: {', '.join(keys)}")
    print(f"Files found: {len(md_files)}")
    print(f"{'=' * 60}\n")

    processed = 0
    conflicts_count = 0
    skipped_count = 0
    global_choice = None

    for md_file in md_files:
        result, global_choice = process_file(md_file, keys, dry_run, interactive, global_choice)
        if result:
            processed += 1
            if result.get('conflicts'):
                conflicts_count += 1
                if result.get('skipped'):
                    skipped_count += 1

        if global_choice == 'ignore_all':
            remaining = len(md_files) - md_files.index(md_file) - 1
            if remaining > 0:
                print(f"\n⏭️  Skipped remaining {remaining} files")
            break

    print(f"\n{'=' * 60}")
    print(f"Files processed: {processed}/{len(md_files)}")
    if conflicts_count > 0:
        print(f"⚠️  Conflicts detected: {conflicts_count}")
        if skipped_count > 0:
            print(f"   Files skipped: {skipped_count}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description='Convert inline metadata to YAML frontmatter',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python script.py /path/to/vault --data id type
  python script.py . --data status priority --execute
  python script.py ~/Documents/Obsidian --data category tags author
        """
    )
    parser.add_argument('vault_path', nargs='?', default='.',
                        help='Path to Obsidian vault (default: current directory)')
    parser.add_argument('--data', nargs='+', required=True,
                        help='List of metadata keys to extract (e.g., id type status)')
    parser.add_argument('--dry-run', action='store_true', default=True,
                        help='Simulation mode (default)')
    parser.add_argument('--execute', action='store_true',
                        help='Execute actual conversion')
    parser.add_argument('--no-interactive', action='store_true',
                        help='Non-interactive mode: skip files with conflicts')

    args = parser.parse_args()

    VAULT_PATH = args.vault_path
    KEYS = args.data
    DRY_RUN = not args.execute
    INTERACTIVE = not args.no_interactive

    print("\n⚠️  WARNING ⚠️")
    print("Make a BACKUP of your vault before running in actual mode!\n")

    if DRY_RUN:
        print("DRY RUN mode enabled - No files will be modified\n")
        input("Press Enter to start simulation...")
    else:
        print("⚠️  ACTUAL MODE - Files WILL be modified ⚠️")
        if INTERACTIVE:
            print("Interactive mode: you will be prompted in case of conflict\n")
        else:
            print("Non-interactive mode: conflicts will be skipped\n")
        confirmation = input("Type 'CONFIRM' to continue: ")
        if confirmation != "CONFIRM":
            print("Cancelled.")
            sys.exit()

    process_vault(VAULT_PATH, KEYS, DRY_RUN, INTERACTIVE)
