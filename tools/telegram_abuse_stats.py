#!/usr/bin/env python3
import argparse
import csv
import json
import os
from datetime import datetime, date
from typing import Dict, Iterable, Optional
import re
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# ============================================================
# Configuration
# ============================================================

REASON_BY_SOURCE = {
    "Stop Child Abuse": "child_abuse",
    "ISIS Watch": "terrorism_isis",
}

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

CSV_FIELDS = [
    "event_date",
    "publish_date",
    "reason",
    "source",
    "banned_count",
    "monthly_total",
]

# ============================================================
# Regex
# ============================================================

BANNED_RE = re.compile(
    r"(?P<count>\d+)\s+(?:ISIS\s+|terrorist\s+)?(?:bots|groups)?\s*and\s*channels",
    re.I
)
DATE_RE = re.compile(
    r"banned\s+on\s+(?P<month>[A-Za-z]+),\s*(?P<day>\d{1,2})",
    re.I
)
MONTH_TOTAL_RE = re.compile(
    r"Total\s+this\s+month:\s*(?P<total>\d+)",
    re.I
)

# ============================================================
# Helpers
# ============================================================

def load_json(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def normalize_text(text_field) -> str:
    if isinstance(text_field, str):
        return text_field
    if isinstance(text_field, list):
        out = []
        for el in text_field:
            if isinstance(el, str):
                out.append(el)
            elif isinstance(el, dict) and "text" in el:
                out.append(el["text"])
        return "".join(out)
    return ""

def extract_event_date(text: str, publish_dt: datetime) -> date:
    m = DATE_RE.search(text)
    if not m:
        return publish_dt.date()
    month_name = m.group("month").lower()
    day = int(m.group("day"))
    month = MONTHS[month_name]
    year = publish_dt.year
    if month > publish_dt.month:
        year -= 1
    return date(year, month, day)

# ============================================================
# Parsing
# ============================================================

def parse_message(msg: Dict, source: str) -> Optional[Dict]:
    if msg.get("type") != "message":
        return None
    text = normalize_text(msg.get("text", ""))
    if not text:
        return None
    m_banned = BANNED_RE.search(text)
    m_total = MONTH_TOTAL_RE.search(text)
    publish_dt = datetime.fromisoformat(msg["date"])
    if not m_banned or not m_total:
        return None
    event_dt = extract_event_date(text, publish_dt)
    banned_count = int(m_banned.group("count"))
    return {
        "event_date": event_dt,
        "publish_date": publish_dt.date(),
        "reason": REASON_BY_SOURCE.get(source, "unknown"),
        "source": source,
        "banned_count": banned_count,
        "monthly_total": int(m_total.group("total")),
    }

def iter_entries(data: Dict) -> Iterable[Dict]:
    source = data.get("name", "unknown")
    for msg in data.get("messages", []):
        parsed = parse_message(msg, source)
        if parsed:
            yield parsed

# ============================================================
# CSV Update
# ============================================================

def update_csv_with_json(csv_path: str, data: Dict) -> pd.DataFrame:
    """
    Updates an existing CSV with a Telegram JSON dump.
    Returns the updated DataFrame.
    """
    # Read existing CSV if present
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path, parse_dates=["event_date", "publish_date"])
    else:
        df = pd.DataFrame(columns=CSV_FIELDS)

    # Extract new entries from JSON
    new_rows = list(iter_entries(data))
    if not new_rows:
        return df  # nothing new

    df_new = pd.DataFrame(new_rows)

    # Convert dates to Timestamp for consistency
    df_new["event_date"] = pd.to_datetime(df_new["event_date"])
    df_new["publish_date"] = pd.to_datetime(df_new["publish_date"])

    if not df.empty:
        df["event_date"] = pd.to_datetime(df["event_date"])
        df["publish_date"] = pd.to_datetime(df["publish_date"])
        df = pd.concat([df, df_new], ignore_index=True)
        df.drop_duplicates(subset=["event_date", "source", "banned_count"], inplace=True)
    else:
        df = df_new

    # Rewrite complete CSV
    df.sort_values("event_date", inplace=True)
    df.to_csv(csv_path, index=False, columns=CSV_FIELDS)
    return df

def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["event_date", "publish_date"])
    return df

# ============================================================
# Graph & stats
# ============================================================

def draw_graph(dfs, labels, remove_outliers_flag=False):
    plt.figure(figsize=(12,6))
    for df, label in zip(dfs, labels):
        if df.empty:
            continue
        df_sorted = df.sort_values("event_date")
        df_plot = df_sorted
        if remove_outliers_flag:
            df_plot = remove_outliers(df_sorted)  # removes extreme 1%
        plt.plot(df_plot["event_date"], df_plot["banned_count"], label=label, marker=None)
    plt.xlabel("Date")
    plt.ylabel("Banned count")
    plt.title("Telegram banned entities over time")
    plt.legend()
    plt.grid(True)
    plt.gca().xaxis.set_minor_locator(mdates.MonthLocator())
    plt.gca().xaxis.set_major_locator(mdates.YearLocator())
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.gcf().autofmt_xdate()
    plt.tight_layout()
    plt.show()


def print_stats(df, label, show_monthly=True):
    print(f"\nStatistics for {label}:")
    if df.empty or "banned_count" not in df.columns:
        print("No data available.")
        return
    print(f"Total events: {len(df)}")
    print(f"Average per day: {df['banned_count'].mean():.0f}")
    df["year"] = df["event_date"].dt.year
    yearly_avg = df.groupby("year")["banned_count"].mean()
    print("Average per year:")
    print(yearly_avg.round(0).to_string())
    if show_monthly:
        df["month"] = df["event_date"].dt.to_period("M")
        monthly_avg = df.groupby("month")["banned_count"].mean()
        print("Average per month:")
        print(monthly_avg.round(0).to_string())


def compare_stats(dfs, labels):
    print("\nComparison statistics (yearly averages):")

    # Build comparative DataFrame by year
    combined = pd.DataFrame()
    for df, label in zip(dfs, labels):
        if df.empty:
            continue
        df["year"] = df["event_date"].dt.year
        yearly_avg = df.groupby("year")["banned_count"].mean().round(0)
        yearly_avg.name = label
        if combined.empty:
            combined = yearly_avg.to_frame()
        else:
            combined = combined.join(yearly_avg, how="outer")

    combined = combined.fillna(0).astype(int)
    print(combined)


def remove_outliers(df: pd.DataFrame, lower_pct=0.01, upper_pct=0.99) -> pd.DataFrame:
    """
    Removes outliers based on quantiles.
    lower_pct and upper_pct are quantiles (0.01 = 1%)
    """
    lower = df["banned_count"].quantile(lower_pct)
    upper = df["banned_count"].quantile(upper_pct)
    df_filtered = df[(df["banned_count"] >= lower) & (df["banned_count"] <= upper)]
    return df_filtered


# ============================================================
# Main
# ============================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", help="Telegram JSON export")
    ap.add_argument("--load", help="Load CSV")
    ap.add_argument("--out-file", help="CSV output file (if --dump used)")
    ap.add_argument("--draw", action="store_true", help="Draw graph")
    ap.add_argument("--compare", help="Compare with another CSV")
    ap.add_argument("--rem-outliers", action="store_true", help="Remove top/bottom 1% outliers before plotting")
    args = ap.parse_args()

    dfs = list()
    labels = list()

    # Load or parse first dataset
    if args.dump:
        if not args.out_file:
            raise ValueError("Please provide --out-file when using --dump")
        data = load_json(args.dump)
        df = update_csv_with_json(args.out_file, data)
        dfs.append(df)
        labels.append(df["source"].iloc[0] if not df.empty else "Dataset1")
    elif args.load:
        df = load_csv(args.load)
        dfs.append(df)
        labels.append(df["source"].iloc[0] if not df.empty else os.path.basename(args.load))
    else:
        raise ValueError("Either --dump or --load must be specified")

    # Compare dataset if specified
    if args.compare:
        df2 = load_csv(args.compare)
        dfs.append(df2)
        labels.append(df2["source"].iloc[0] if not df2.empty else os.path.basename(args.compare))

    # Draw graph if requested
    if args.draw:
        draw_graph(dfs, labels, args.rem_outliers)

    # Print stats
    if len(dfs) == 1:
        print_stats(dfs[0], labels[0], show_monthly=True)
    else:
        compare_stats(dfs, labels)

    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()
    