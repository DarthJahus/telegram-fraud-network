# Telegram Entity Statistics

A tool for analyzing and tracking statistics from markdown-formatted Telegram entity files. This script scans directories containing entity documentation, parses them using the MDML format, and generates comprehensive statistics about entity statuses, types, and activity tags.

## Purpose

This tool serves to:

1. **Track Network Evolution**: Monitor the status of documented Telegram entities (channels, groups, users, bots) over time
2. **Identify Patterns**: Analyze which types of entities are most frequently banned, deleted, or remain active
3. **Tag Analysis**: Understand the distribution of abuse categories through activity tags

The script was created to efficiently analyze large collections of entity documentation maintained in the Telegram Fraud Network project.

## How It Works

The script processes markdown files that document Telegram entities using the MDML (Markdown Metadata Language) format. Each entity file contains structured fields such as:

- **Type**: Entity type (channel, group, user, bot)
- **Status**: Current status with historical tracking (active, banned, deleted, unknown)
- **Activity**: Tags describing the entity's abuse category (`#bankaccounts`, `#crypto`, `#hub`)

The script:
1. Scans a directory for `.md` files
2. Parses each file using the `telegram_mdml` middleware
3. Extracts the most recent status for each entity
4. Collects activity tags (any tag starting with `#`)
5. Generates statistics and displays them in organized sections

## Prerequisites

This script requires:

- **mdml** package: Core MDML parsing library
- **telegram_mdml** module: Middleware for Telegram entity parsing (included as submodule in this repository)

The `telegram_mdml` module is located in `telegram-fraud-network/tools/telegram_mdml/` and should be accessible in your Python path.

## Usage

### Basic Usage

Analyze all entity files in a directory:

```bash
python entity_stats.py /path/to/entities/
```

This will:
- Scan all `.md` files in the specified directory
- Parse each entity file
- Display comprehensive statistics

### Example with Project Structure

If your entities are organized like this:
```
telegram-fraud-network/
├── tools/
│   ├── telegram_mdml/
│   └── entity_stats.py
└── entities/
    ├── channel_123456.md
    ├── group_789012.md
    ├── user_345678.md
    └── ...
```

Run from the `tools` directory:
```bash
python entity_stats.py ../entities/
```

## Output Format

The script generates three main sections of statistics:

### 📊 Global Overview

Shows overall entity statistics including:
- Total number of entities
- Banned entities count and percentage
- Deleted entities count and percentage
- Unknown status entities
- Active entities count and percentage

### 🧩 Entry Types

Breaks down statistics by entity type:
- Channel
- Group
- User
- Bot
- Unknown

For each type, displays the count and distribution of unknown, deleted, and banned statuses.

### 🏷️ Tag Analysis

Analyzes activity tags grouped into predefined categories:

**💳 FINANCIAL FRAUD**
- `#bankaccounts` - Banking fraud schemes
- `#checking` - Checking account fraud
- `#carding` - Credit card fraud

**⛏ CRYPTO / SCAMS**
- `#crypto` - Cryptocurrency scams
- `#investment_scam` - Investment fraud schemes

**🧰 INFRA / NOISE**
- `#hub` - Network hubs and aggregators
- `#backup` - Backup or mirror channels

**📦 OTHER TAGS**
- Any tags not in the predefined categories

## Example Output

```
──────────────────────────────────────────────────
📊 GLOBAL OVERVIEW
──────────────────────────────────────────────────
📄 Total entries        :  418
🔨 Banned               :   63  15.1%
🗑️ Deleted              :   21   5.0%
❓ Unknown              :  129
🟢 Active               :  205  49.0%

──────────────────────────────────────────────────
🧩 ENTRY TYPES
──────────────────────────────────────────────────
Channel   : 130 •   51 ❓  39.2% •   44 🔨  33.8%
Group     :  44 •   19 ❓  43.2% •   15 🔨  34.1%
User      : 187 •   16 ❓   8.6% •   21 🗑️  11.2%
Bot       :   6
Unknown   :  51 •   43 ❓  84.3% •    4 🔨   7.8%

──────────────────────────────────────────────────
🏷️  TAG ANALYSIS
──────────────────────────────────────────────────
💳 FINANCIAL FRAUD
  #bankaccounts        62   14.8%
  #checking            51   12.2%
  #carding             12    2.9%

⛏ CRYPTO / SCAMS
  #crypto               7    1.7%
  #investment_scam      5    1.2%

🧰 INFRA / NOISE
  #hub                  6    1.4%
  #backup              22    5.3%

📦 OTHER TAGS
  #spam                 6    1.4%
```

## Notes

### Entity Status

The script uses the **most recent status** from each entity's history. This is automatically determined by the `telegram_mdml` module, which:
- Prioritizes statuses with dates (most recent first)
- Falls back to the last status in document order if no dates are present
- Ignores strikethrough statuses (unless explicitly requested)

Valid statuses are:
- `active` - Entity is currently active
- `banned` - Entity has been banned by Telegram
- `deleted` - Entity has been deleted
- `unknown` - Status cannot be determined
- `id_mismatch` - Entity ID doesn't match expected value

### Activity Tags

Tags are extracted from the `activity` field in entity files. The field can contain:
- **Array values**: Multiple tags in a list
- **Single values**: One or more tags in text format

Only tags starting with `#` are counted. Tags are case-sensitive.

### File Parsing

If a file cannot be parsed (invalid MDML format, missing required fields, etc.), the script:
- Prints a warning to stderr
- Continues processing other files
- Does not include the failed file in statistics

### Empty Directories

If no `.md` files are found in the specified directory, the script will:
- Display a warning
- Exit with an error message

## Integration with Telegram Fraud Network

This tool is part of the [Telegram Fraud Network](https://github.com/DarthJahus/telegram-fraud-network/) project and is located in `tools/entity_stats.py`.

The script works in conjunction with:
- **telegram_mdml**: MDML parsing middleware (submodule in `tools/telegram_mdml/`)
- **Entity documentation**: Markdown files documenting fraudulent Telegram entities

## License

This tool is part of the Telegram Fraud Network project. See the main repository for license information.