# Telegram Status Checker

Automated tool for checking and tracking the status of Telegram entities (channels, groups, users, bots) documented in markdown files.

## Purpose

This script is designed to work with the [Telegram Fraud Network](https://github.com/DarthJahus/telegram-fraud-network/) documentation method. It:

- Checks if documented Telegram entities are still active, banned, or deleted
- Updates markdown files with timestamped status entries
- Detects when usernames have been reused by different accounts
- Provides filtering and skip options to optimize API usage
- Maintains a historical record of status changes

## Requirements

### Python Dependencies

```bash
pip install telethon
```

### Telegram API Credentials

You need a Telegram API ID and hash. Obtain them from [my.telegram.org](https://my.telegram.org).

Create the following directory structure:

```
.secret/
├── api_id           # Your API ID (plain text)
├── api_hash         # Your API hash (plain text)
└── default.mobile   # Your phone number (+XXXXXXXXXXX)
```

For multiple accounts, create additional `.mobile` files with different names (e.g., `alt.mobile`).

## Markdown File Format

The script expects markdown files with the following structure:

```markdown
---
type: user
---
id: `123456789`

status:
- `active`, `2026-01-18 23:16`

username: `@example` ([link](https://t.me/example))

name: `Display Name`
```

**Required fields:**
- `type:` - entity type (user, channel, group, bot)
- `status:` - block where status entries will be added
- At least one identifier: `username:` or `invite:` link

**Optional but recommended:**
- `id:` - entity ID for username reuse detection

## Usage

### Basic Usage

Check all entities in a directory:

```bash
python check_status_tg.py --path /path/to/markdown/files
```

### Common Options

**Filter by type:**
```bash
python check_status_tg.py --path . --type user
python check_status_tg.py --path . --type channel
```

**Skip recently checked entities:**
```bash
# Skip entities checked in the last 24 hours
python check_status_tg.py --path . --skip-time 86400
python check_status_tg.py --path . --skip-time "24*60*60"

# Skip entities checked in the last 6 hours
python check_status_tg.py --path . --skip-time "6*60*60"
```

**Skip specific statuses:**
```bash
# Skip entities with 'banned' status
python check_status_tg.py --path . --skip banned

# Skip multiple statuses
python check_status_tg.py --path . --skip banned deleted
```

**Combine filters:**
```bash
# Skip channels checked in the last 12 hours
python check_status_tg.py --path . --type channel --skip-time "12*60*60"

# Skip recently checked OR banned/deleted entities
python check_status_tg.py --path . --skip-time "24*60*60" --skip banned deleted
```

**Dry run mode:**
```bash
# Preview changes without modifying files
python check_status_tg.py --path . --dry-run
```

**Multiple accounts:**
```bash
# Use a different Telegram account
python check_status_tg.py --path . --user alt
```

## Status Types

The script returns the following status values:

- **`active`** - Entity exists and is accessible
- **`banned`** - Confirmed platform-wide ban (restricted for all platforms)
- **`deleted`** - Account has been deleted (users only)
- **`id_mismatch`** - Username exists but belongs to a different account
- **`unknown`** - Cannot determine exact status (private channel, invalid invite, username changed, etc.)
- **`error_*`** - Unexpected error occurred

## Important Behaviors

### Username Reuse Detection

When an entity has both a `username:` and an `id:` field, the script verifies that the current entity ID matches the documented ID. This detects cases where:

1. Original account was deleted or changed username
2. Someone else claimed the same username
3. The username now points to a completely different entity

Status `id_mismatch` indicates the username has been reused.

### Unknown Status Re-checking

Entities with `unknown` status are **always re-checked**, regardless of `--skip-time` settings. This is because:

- Private channels may become public
- Changed usernames may be restored
- Temporary errors may resolve
- Invalid invites may be replaced

Other statuses (`active`, `banned`, `deleted`) respect the `--skip-time` parameter.

### Status History

The script maintains up to 10 status entries per file, with timestamps:

```markdown
status:
- `active`, `2026-01-18 22:30`
- `unknown`, `2026-01-17 14:15`
- `active`, `2026-01-16 08:00`
```

When the limit is reached, the middle entry is removed to preserve both recent and oldest records.

## Output Example

```
📂 150 .md files found
🔍 Filter: all

⏳ tg_123456.md: @example... ✅ active
⏳ tg_234567.md: +AbCdEf... ❓ unknown
⏳ tg_345678.md: @scammer... 🔨 banned
  📋 Reason: spam
  💾 File updated
⏳ tg_456789.md: @reused... ⚠️ id_mismatch
  ⚠️  Expected ID: 111111111, found ID: 999999999

══════════════════════════════════════════════════════════════
📊 RESULTS
══════════════════════════════════════════════════════════════
Total checked:  120
✅ Active:      85
🔨 Banned:      12
🗑️ Deleted:     8
⚠️ ID Mismatch: 2
❓ Unknown:     13
❌ Errors:      0

⏭️ Skipped (total):      30
   └─ Recently checked:  25
   └─ By status:         5
══════════════════════════════════════════════════════════════
```

## Rate Limiting

The script includes a 20-second delay between checks by default (`SLEEP_BETWEEN_CHECKS`). This prevents Telegram API rate limits.

If you encounter `FloodWaitError`, the script will automatically wait the required time.

## Configuration

Edit these constants in the script if needed:

```python
SLEEP_BETWEEN_CHECKS = 20  # seconds between each check
MAX_STATUS_ENTRIES = 10    # maximum status history per file
```

## Integration with Telegram Fraud Network

This script is designed to work with the documentation method described in the [main repository](https://github.com/DarthJahus/telegram-fraud-network/). It automates the status checking process while maintaining the manual observation and documentation approach.

The script updates markdown files in place, preserving the manual documentation and adding automated status tracking.

## Troubleshooting

**"Mobile file not found"**
- Create `.secret/default.mobile` with your phone number
- Format: `+XXXXXXXXXXX`

**"No 'status:' block found"**
- Add `status:` line to your markdown file
- The script will populate it with status entries

**"No identifier found"**
- Add either `username: @example` or `invite: https://t.me/+hash` to the file

**Rate limit errors**
- Increase `SLEEP_BETWEEN_CHECKS`
- Use `--skip-time` to avoid re-checking recently verified entities
- The script handles `FloodWaitError` automatically

## License

This tool is part of the Telegram Fraud Network project. See the main repository for license information.
