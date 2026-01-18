import csv
import sys
from collections import Counter, defaultdict


def load_entries(path):
    """Load and parse CSV entries."""
    entries = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entries.append({
                "name": row["file name"].strip(),
                "tags": [t.strip() for t in (row["file tags"] or "").split(",") if t.strip()],
                "type": (row.get("type") or "").strip().lower() or "unknown",
                "banned": row["banned"] == "true",
                "deleted": row["deleted"] == "true"
            })
    return entries


def compute_stats(entries):
    """Compute global statistics from entries."""
    total = len(entries)
    banned = sum(1 for e in entries if e["banned"])
    deleted = sum(1 for e in entries if e["deleted"])
    active = total - (banned + deleted)
    active_pct = (active / total * 100) if total else 0

    return {
        "total": total,
        "banned": banned,
        "deleted": deleted,
        "active": active,
        "active_pct": active_pct
    }


def compute_type_stats(entries):
    """Compute statistics per entry type."""
    types_data = defaultdict(lambda: {"total": 0, "banned": 0, "deleted": 0})
    for entry in entries:
        typ = entry["type"]
        types_data[typ]["total"] += 1
        if entry["banned"]:
            types_data[typ]["banned"] += 1
        if entry["deleted"]:
            types_data[typ]["deleted"] += 1
    return types_data


def format_type_line(typ, data):
    """Format a single type statistics line."""
    t = data["total"]
    b = data["banned"]
    d = data["deleted"]

    parts = [f"{typ.capitalize():<10}: {t:>3}"]

    if d > 0:
        d_pct = (d / t * 100) if t else 0
        parts.append(f"•  {d:>3} 🗑️ {d_pct:5.1f}%")

    if b > 0:
        b_pct = (b / t * 100) if t else 0
        parts.append(f"•  {b:>3} 🔨 {b_pct:5.1f}%")

    return " ".join(parts)


def print_global_stats(stats):
    """Print global overview section."""
    line = "─" * 50
    print(line)
    print("📊 GLOBAL OVERVIEW")
    print(line)
    print(f"📁 Total entries        : {stats['total']:4.0f}")
    print(f"🔨 Banned               : {stats['banned']:4.0f}")
    print(f"🗑️ Deleted              : {stats['deleted']:4.0f}")
    print(f"🔴 Active               : {stats['active']:4.0f} {stats['active_pct']:5.1f}%\n")


def print_type_stats(types_data):
    """Print entry types section."""
    line = "─" * 50
    print(line)
    print("🧩 ENTRY TYPES")
    print(line)

    type_order = ["user", "group", "channel", "channels", "bot", "website", "unknown"]
    for typ in type_order:
        if typ in types_data:
            print(format_type_line(typ, types_data[typ]))
    print()


def print_tag_stats(entries, total):
    """Print tag analysis section."""
    line = "─" * 50
    all_tags = Counter()
    for entry in entries:
        all_tags.update(entry["tags"])

    print(line)
    print("🏷️  TAG ANALYSIS")
    print(line)

    categories = {
        "💳 FINANCIAL FRAUD": ["#bankaccounts", "#checking", "#carding"],
        "⛏  CRYPTO / SCAMS": ["#crypto", "#investment_scam"],
        "🧰 INFRA / NOISE": ["#hub", "#backup"],
    }

    used_tags = set(t for group in categories.values() for t in group)

    for title, tag_list in categories.items():
        print(title)
        for tag in tag_list:
            count = all_tags.get(tag, 0)
            pct = (count / total * 100) if total else 0
            print(f"  {tag:<18} {count:>4}  {pct:5.1f}%")
        print()

    other_tags = [(t, c) for t, c in all_tags.items() if t not in used_tags]
    if other_tags:
        print("📦 OTHER TAGS")
        for tag, count in sorted(other_tags, key=lambda x: x[1], reverse=True):
            pct = (count / total * 100) if total else 0
            print(f"  {tag:<18} {count:>4}  {pct:5.1f}%")


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <file.csv>")
        sys.exit(1)

    path = sys.argv[1]

    entries = load_entries(path)
    stats = compute_stats(entries)
    types_data = compute_type_stats(entries)

    print_global_stats(stats)
    print_type_stats(types_data)
    print_tag_stats(entries, stats["total"])


if __name__ == "__main__":
    main()
