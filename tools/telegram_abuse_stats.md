# Telegram Abuse Statistics

A tool for tracking and analyzing Telegram's official ban statistics from their abuse reporting channels. This script parses ban announcements, generates historical data and produces graphs showing the evolution of content moderation on Telegram.

## Purpose

This tool serves two main purposes:

1. **Curiosity & Research** - Understand how Telegram's moderation efforts have evolved over time for different abuse categories
2. **Data Reproducibility** - Enable anyone to reproduce published statistics and graphs, or update them with newer data

The script was created to analyze and visualize data from Telegram's official abuse reporting channels in a more efficient way than manual spreadsheet work.

## How It Works

Telegram operates official channels that announce daily ban statistics:

- **[@isiswatch](https://t.me/isiswatch)**: Reports bans of terrorist content (used to be ISIS-related)
- **[@stopca](https://t.me/stopca)**: Reports bans of child abuse content

These channels post daily updates in a consistent format.

This script:
1. Parses Telegram JSON exports from these channels
2. Extracts ban counts, dates, and monthly totals
3. Stores data in CSV format for easy analysis
4. Generates graphs and statistics

### Message Format Examples

**ISIS Watch (@isiswatch):**
```
1312 terrorist bots and channels banned on January, 27.
Total this month: 16050

Report terrorist content using the in-app 'Report' button or to abuse@telegram.org.
```

**Stop Child Abuse (@stopca):**
```
1830 groups and channels related to child abuse banned on January, 30.
Total this month: 51889

Report child abuse using the in-app 'Report' button or to stopCA@telegram.org.
```

### Data Source

You need JSON exports from Telegram channels. These can be obtained using **Telegram Desktop**.

1. Open **Telegram Desktop** (`tdesktop.exe`)
2. Navigate to the channel you want to export:
   - [@isiswatch](https://t.me/isiswatch) for terrorism-related bans
   - [@stopca](https://t.me/stopca) for child abuse-related bans
3. Click on the channel name, then on **⋮** (three dots) → **Export chat history**
4. In the export dialog:
   - **Format**: JSON
   - **Media**: Uncheck all (we only need text)
   - **Size limit**: Not important
   - **Date range**: Select all or desired range
5. Export to a folder (example: `isiswatch_export/` or `stopca_export/`)

The export will create a `result.json` file in the selected folder.

### Step 2: Locate the JSON File

After export, you should have:
```
your_export_folder/
└── result.json
```

This `result.json` is what you'll use with the script.

## Usage

### First Time: Create CSV from JSON Export

Parse a JSON export and create a CSV database:

```bash
python telegram_abuse_stats.py --dump path/to/result.json --out-file isiswatch.csv
```

This will:
- Parse all messages in the JSON
- Extract ban statistics
- Create/update the CSV file
- Display basic statistics

### Load and Analyze Existing CSV

View statistics from an existing CSV:

```bash
python telegram_abuse_stats.py --load isiswatch.csv
```

### Draw Graphs

Visualize the data with a time-series graph:

```bash
python telegram_abuse_stats.py --load isiswatch.csv --draw
```

### Compare Two Datasets

Compare statistics from different sources side-by-side:

```bash
python telegram_abuse_stats.py --load isiswatch.csv --compare stopca.csv --draw
```

This will:
- Show comparative yearly statistics
- Draw both datasets on the same graph for visual comparison

### Remove Outliers

For cleaner graphs, remove extreme values (top/bottom 1%):

```bash
python telegram_abuse_stats.py --load isiswatch.csv --draw --rem-outliers
```

### Update Existing CSV with New Data
If you export new data later and want to update your CSV:

```bash
python telegram_abuse_stats.py --dump path/to/new_export.json --out-file isiswatch.csv
```

The script automatically:
- Merges new entries with existing data
- Removes duplicates
- Maintains chronological order

## Command-Line Arguments
```
usage: telegram_abuse_stats.py [--dump DUMP] [--load LOAD] [--out-file OUT_FILE]
                               [--draw] [--compare COMPARE] [--rem-outliers]

options:
  --dump DUMP           Path to Telegram JSON export file
  --load LOAD           Path to existing CSV file to analyze
  --out-file OUT_FILE   CSV output file (required when using --dump)
  --draw                Generate and display time-series graph
  --compare COMPARE     Path to second CSV file for comparison
  --rem-outliers        Remove top/bottom 1% outliers before plotting
```

## CSV Format

The script generates CSV files with the following columns:

| Column | Description | Example |
|--------|-------------|---------|
| `event_date` | Date when entities were banned | `2024-01-27` |
| `publish_date` | Date when the message was posted | `2024-01-28` |
| `reason` | Category of abuse | `terrorism_isis` or `child_abuse` |
| `source` | Source channel name | `ISIS Watch` or `Stop Child Abuse` |
| `banned_count` | Number of entities banned | `1312` |
| `monthly_total` | Running total for that month | `16050` |

## Output Examples

### Statistics Output
```
Statistics for ISIS Watch:
Total events: 1247
Average per day: 1523
Average per year:
2020    1234
2021    1456
2022    1589
2023    1612
2024    1523

Average per month:
2024-01    1550
2024-02    1498
2024-03    1521
```

### Comparison Output
```
Comparison statistics (yearly averages):
      ISIS Watch  Stop Child Abuse
2020        1234              2845
2021        1456              3012
2022        1589              3234
2023        1612              3456
2024        1523              3398
```

### Graph Output
The `--draw` option opens an interactive matplotlib window showing:
- X-axis: Timeline (dates)
- Y-axis: Number of banned entities
- Line plot showing trends over time
- Multiple datasets when using `--compare`

## Notes

### Data Accuracy
- Statistics reflect what Telegram publicly reports
- The script parses exactly what's in the messages
- Some messages may not match the expected format (rare) and will be skipped
- Duplicates are automatically removed based on event date, source and count

### Limitations
- Only works with the two official channels (hardcoded)
- Requires manual JSON exports (no automated scraping)
- Depends on Telegram maintaining consistent message format

## Integration with Telegram Fraud Network
This tool is part of the [Telegram Fraud Network](https://github.com/DarthJahus/telegram-fraud-network/) project and is located in `tools/telegram_abuse_stats.py`.

## License
This tool is part of the Telegram Fraud Network project. See the main repository for license information.
