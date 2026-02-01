# Telegram Status Checker

Automated tool for checking and tracking the status of Telegram entities (channels, groups, users, bots) documented in markdown files.

## Purpose

This script is designed to work with the [Telegram Fraud Network](https://github.com/DarthJahus/telegram-fraud-network/) documentation method. It:

- Checks if documented Telegram entities are still active, banned, or deleted
- Updates markdown files with timestamped status entries
- Detects when usernames have been reused by different accounts
- Recovers and writes entity IDs from invite links
- Discover usernames
- Tracks username changes
- Provides filtering and skip options to optimize API usage
- Maintains a historical record of status changes

## Requirements

### Python Dependencies

```bash
pip install telethon
```

**Note:** The [`telegram_mdml`](https://github.com/darthjahus/telegram_mdml) module is included as a submodule in this repository.

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

### Alternative Formats

The script also supports block formats for multiple usernames or invites (with or without date / details / strikethrough):

```markdown
username:
- `@example1`
- `@example2`, `2026-01-30`

invite:
- ~~https://t.me/+O1D1NV1T3~~ (expried)
- https://t.me/+ABC123xyz
- https://t.me/+DEF456uvw, `2026-02-01`
```

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

**Ignore specific statuses:**

The `--ignore` option allows you to check entities, but skip updating their files based on the **check result**. This is useful when you want to verify status without documenting certain outcomes:

```bash
# Check entities, but don't update files if the result is 'active'
python check_status_tg.py --path . --ignore active

# Ignore multiple result statuses
python check_status_tg.py --path . --ignore active unknown

# Useful for monitoring without affecting documentation of stable entities
python check_status_tg.py --path . --ignore active --skip-time "12*60*60"
```

**Example:**
A file currently has `status: active`.
You check it and find it's now `unknown`
With `--ignore unknown`, the file will **not** be updated (because the check result is `unknown`).

**Difference between `--skip` and `--ignore`:**
- `--skip <status>`: Don't check entities whose **current/last** status matches (saves API calls)
- `--ignore <status>`: Check all entities, but don't update files when the **check result** matches (useful for monitoring)

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

**Logging:**
```bash
# Save output to a log file
python check_status_tg.py --path . --log output.log
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

### ID Recovery from Invite Links

When checking entities via invite links, the script can recover the entity ID. 
Use `--write-id` to automatically write recovered IDs to MDML files.

This is useful for:
- Enabling ID-based checking (faster and more reliable)
- Tracking entity changes even after invite link expiration

### Username Discovery and Tracking

The script automatically detects and reports:
- **New usernames** - When an entity gains a username (reported as "discovered")
- **Changed usernames** - When an existing username changes to a different one

These changes are displayed in the final summary.

### Unknown Status Re-checking

Entities with `unknown` status are **always re-checked** by default, regardless of `--skip-time` settings. This is because:
- Private channels may become public
- Changed usernames may be restored
- Temporary errors may resolve
- Invalid invites may be replaced

Use `--no-skip-unknown` to skip these entities as well.

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
📂 301 .md files found
🔍 Filter: all

📡 Connecting to Telegram (user: watcher)...
✅ Connected!

🧻 tg_+123BfldT567kMzRh.md
  📨 Fallback: Checking 1 invite(s)...
    ⏳ [1/1] +123BfldT567kMzR...... ❓ unknown
  💾 File updated

🧻 tg_6544778986.md
🆔 Checking by ID: 6544778986... 🔨 banned
  🔄 STATUS CHANGE: unknown → banned
  📋 Reason: porn
  💬 Text: This channel can't be displayed because it was used to spread calls to violence.
  💾 File updated

🧻 tg_+985412365QM5MGEx ❓.md
   Skipped: No identifier found

🧻 tg_+985412365qtmOGIx.md
  📨 Fallback: Checking 1 invite(s)...
    ⏳ [1/1] +985412365qtmOGI...... ❓ unknown
  ⚠️ No 'status:' block found in tg_+985412365qtmOGIx.md

🧻 tg_5988508437.md
🆔 Checking by ID: 5988508437... 🔨 banned
  🔄 STATUS CHANGE: active → banned
  📋 Reason: terms
  💬 Text: This channel can't be displayed because it violated Telegram's Terms of Service.
  💾 File updated
 
🧻 tg_985412365.md
🆔 Checking by ID: 985412365... 🔥 active
  💾 File updated

🧻 tg_9854123651.md
🆔 Checking by ID: 9854123651... ❓ unknown
  👤 Fallback: Checking @Beb2Beers... ❓ unknown
  🔄 STATUS CHANGE: active → unknown
  💾 File updated

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 RESULTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total checked:  120
🔥 Active:      85
🔨 Banned:      12
🗑️ Deleted:     8
⚠️ ID Mismatch: 2
❓ Unknown:     13
❌ Errors:      0

⏭️ Skipped (total):      30
   ├─ Recently checked:  25
   ├─ By status:         5
   └─ By type:           0

🙈 Ignored (checked but not updated): 5

💊 Methods used:
   ├─ By ID:       95
   ├─ By username: 15
   └─ By invite:   10
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📰 IDs recovered from invites: 5
File: tg_invite123.md → ID: 123456789 (written ✓)
File: tg_invite456.md → ID: 987654321 (written ✓)

✨ Usernames discovered/changed: 3
File: tg_123.md → @newusername (discovered)
File: tg_456.md → @oldname → @newname (changed)

ℹ️ Done!
```

## Command-Line Arguments Reference

```
usage: check_status_tg.py [-h] --path PATH [--type {all,user,channel,group,bot}]
                          [--skip-time SKIP_TIME] [--skip SKIP [SKIP ...]]
                          [--no-skip-unknown] [--ignore IGNORE [IGNORE ...]]
                          [--write-id] [--dry-run] [--user USER] [--log LOG]

options:
  -h, --help            Show this help message and exit
  --path PATH           Path to directory containing markdown files
  --type {all,user,channel,group,bot}
                        Filter by entity type (default: all)
  --skip-time SKIP_TIME
                        Skip entities checked within N seconds (e.g., 86400 for 24h,
                        or "24*60*60")
  --skip SKIP [SKIP ...]
                        Skip entities with these statuses (e.g., banned deleted)
  --no-skip-unknown     Don't automatically re-check entities with 'unknown' status
  --ignore IGNORE [IGNORE ...]
                        Check entities but don't update files with these statuses
  --write-id            Write recovered IDs to markdown files (from invite links)
  --dry-run             Preview changes without modifying files
  --user USER           Telegram account to use (default: default)
  --log LOG             Log output to file
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

## ToDo
- [ ] Add `--list-invites` to list valid/usage invites
- [ ] Consider using more than 1 account at the same time, and check with every account before settling on a status (helpful for groups where one account has been accepted, and that others can't access)

## License

This tool is part of the Telegram Fraud Network project. See the main repository for license information.
