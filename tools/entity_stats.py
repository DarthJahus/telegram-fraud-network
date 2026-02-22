#!/usr/bin/env python3
import sys
from pathlib import Path
from collections import Counter, defaultdict
from telegram_mdml.telegram_mdml import TelegramEntity


LINE = 70 * "─"


def load_entries(directory_path):
    """Load and parse markdown entries from a directory."""
    entries = []
    directory = Path(directory_path)

    if not directory.exists():
        print(f"Error: Directory {directory_path} does not exist")
        sys.exit(1)

    if not directory.is_dir():
        print(f"Error: {directory_path} is not a directory")
        sys.exit(1)

    # Scan all .md files in the directory
    md_files = list(directory.glob("*.md"))

    if not md_files:
        print(f"Warning: No .md files found in {directory_path}")
        return entries

    for md_file in md_files:
        try:
            entity = TelegramEntity.from_file(md_file)

            # Get the most recent status
            status_obj = entity.get_status()
            status_val = status_obj.value if status_obj else "unknown"

            # Get entity type
            try:
                type_val = entity.get_type()
            except Exception as e:
                type_val = "unknown"

            # Get tags from activity field
            tags = []
            activity_field = entity.doc.get_field('activity')
            if activity_field:
                for field_value in activity_field.values:
                    if field_value.is_array:
                        # Array of values
                        for tag in field_value.array_values:
                            tag = tag.strip()
                            if tag.startswith('#'):
                                if len(tag) > 1:
                                    tags.append(tag.lower())
                    else:
                        # Single value?
                        tag = field_value.value.strip()
                        for _tag_s1 in tag.split():
                            if (_tag_s2:= _tag_s1.strip('`')).startswith('#'):
                                if len(_tag_s2) > 1:
                                    tags.append(_tag_s2.lower())

            entries.append({
                "name": md_file.name,
                "tags": tags,
                "type": type_val,
                "status": status_val
            })

        except Exception as e:
            print(f"Warning: Failed to parse {md_file.name}: {e}", file=sys.stderr)
            continue

    return entries


def compute_stats(entries):
    """Compute global statistics from entries."""
    total = len(entries)
    banned = sum(1 for e in entries if e["status"] == "banned")
    deleted = sum(1 for e in entries if e["status"] == "deleted")
    unknown = sum(1 for e in entries if e["status"] == "unknown")
    active = sum(1 for e in entries if e["status"] == "active")
    active_non_users = sum(1 for e in entries if e["status"] == "active" and e["type"] not in ("user", "bot"))
    active_pct = (active / total * 100) if total else 0
    active_non_users_pct = (active_non_users / total * 100) if total else 0
    banned_pct = (banned / total * 100) if total else 0
    deleted_pct = (deleted / total * 100) if total else 0

    return {
        "total": total,
        "banned": banned,
        "deleted": deleted,
        "unknown": unknown,
        "active": active,
        "active_non_users": active_non_users,
        "active_pct": active_pct,
        "banned_pct": banned_pct,
        "deleted_pct": deleted_pct,
        "active_non_users_pct": active_non_users_pct
    }


def compute_type_stats(entries):
    """Compute statistics per entry type."""
    types_data = defaultdict(lambda: {"total": 0, "active": 0, "banned": 0, "deleted": 0, "unknown": 0})
    for entry in entries:
        typ = entry["type"]
        types_data[typ]["total"] += 1
        if entry["status"] == "active":
            types_data[typ]["active"] += 1
        if entry["status"] == "banned":
            types_data[typ]["banned"] += 1
        if entry["status"] == "deleted":
            types_data[typ]["deleted"] += 1
        if entry["status"] == "unknown":
            types_data[typ]["unknown"] += 1
    return types_data


def format_type_line(typ, data):
    """Format a single type statistics line."""
    t = data["total"]
    a = data["active"]
    b = data["banned"]
    d = data["deleted"]
    u = data["unknown"]

    parts = [f"{typ.capitalize():<10}: {t:>3}"]

    if a > 0:
        a_pct = (a / t * 100) if t else 0
        parts.append(f"•  {a:>3} 🟢 {a_pct:5.1f}%")

    if u > 0:
        u_pct = (u / t * 100) if t else 0
        parts.append(f"•  {u:>3} ❓ {u_pct:5.1f}%")
    else:
        parts.append("                ")

    if d > 0:
        d_pct = (d / t * 100) if t else 0
        parts.append(f"•  {d:>3} 🗑️ {d_pct:5.1f}%")
    elif b > 0:
        b_pct = (b / t * 100) if t else 0
        parts.append(f"•  {b:>3} 🔨 {b_pct:5.1f}%")

    return " ".join(parts)


def print_global_stats(stats):
    """Print global overview section."""
    print(LINE)
    print("📊 GLOBAL OVERVIEW")
    print(LINE)
    print(f"📄 Total entries        : {stats['total']:4.0f}")
    print(f"🔨 Banned               : {stats['banned']:4.0f} {stats['banned_pct']:5.1f}%")
    print(f"🗑️ Deleted              : {stats['deleted']:4.0f} {stats['deleted_pct']:5.1f}%")
    print(f"❓ Unknown              : {stats['unknown']:4.0f}")
    print(f"🟢 Active               : {stats['active']:4.0f} {stats['active_pct']:5.1f}%")
    print(f"🟢 Active non users     : {stats['active_non_users']:4.0f} {stats['active_non_users_pct']:5.1f}%\n")


def print_type_stats(types_data):
    """Print entry types section."""
    print(LINE)
    print("🧩 ENTRY TYPES")
    print(LINE)

    type_order = ["channel", "group", "user", "bot", "unknown"]
    for typ in type_order:
        if typ in types_data:
            print(format_type_line(typ, types_data[typ]))
    print()


def print_tag_stats(entries, total):
    """Print tag analysis section."""
    all_tags = Counter()
    active_tags = Counter()
    for entry in entries:
        all_tags.update(entry["tags"])
        if entry["status"] == "active":
            active_tags.update(entry["tags"])

    print(LINE)
    print("🏷️  TAG ANALYSIS")
    print(LINE)
    print(f" {'TAG':<18}  {'TOTAL':>5}   {'%':>5}  {'ACTIVE':>6}   {'%':>5}")
    print(f" {'─'*18}  {'─'*5}   {'─'*5}  {'─'*6}   {'─'*5}")

    categories = {
        "💳 FINANCIAL FRAUD": ["#bankaccounts", "#checking", "#carding"],
        "⛏ CRYPTO / SCAMS": ["#crypto", "#investment_scam"],
        "🧰 INFRA / NOISE": ["#hub", "#backup"],
    }

    used_tags = set(t for group in categories.values() for t in group)

    for title, tag_list in categories.items():
        print(' ' + title)
        for tag in tag_list:
            count = all_tags.get(tag, 0)
            pct = (count / total * 100) if total else 0
            acount = active_tags.get(tag, 0)
            apct = (acount / total * 100) if total else 0
            print(f"  {tag:<17}  {count:>5}  {pct:5.1f}%  {acount:>6}  {apct:5.1f}%")
        print()

    other_tags = [(t, c) for t, c in all_tags.items() if t not in used_tags]
    if other_tags:
        print(" 📦 OTHER TAGS")
        for tag, count in sorted(other_tags, key=lambda x: x[1], reverse=True):
            pct = (count / total * 100) if total else 0
            acount = active_tags.get(tag, 0)
            apct = (acount / total * 100) if total else 0
            print(f"  {tag:<17}  {count:>5}  {pct:5.1f}%  {acount:>6}  {apct:5.1f}%")


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <directory>")
        print(f"  Scans all .md files in <directory> for Telegram entity stats")
        sys.exit(1)

    directory_path = sys.argv[1]

    entries = load_entries(directory_path)

    if not entries:
        print("No valid entries found.")
        sys.exit(1)

    stats = compute_stats(entries)
    types_data = compute_type_stats(entries)

    print_global_stats(stats)
    print_type_stats(types_data)
    print_tag_stats(entries, stats["total"])
    print()


if __name__ == "__main__":
    main()
