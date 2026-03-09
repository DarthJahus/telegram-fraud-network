#!/usr/bin/env python3
"""
Ban Timeline Analysis
=====================
For each non-User, non-Bot entity with current status BANNED
having all three dates available:

    age_at_discovery = discovered - created      (days)
    survival         = banned - discovered       (days)
    ratio            = age_at_discovery / survival
    pct_life_before  = age_at_discovery / (age_at_discovery + survival) * 100

Usage:
    python timing_analysis.py /path/to/folder
    python timing_analysis.py /path/to/folder --bins 15
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.ticker import MaxNLocator
from scipy.stats import gaussian_kde, spearmanr

from telegram_mdml.telegram_mdml import TelegramEntity, MissingFieldError, InvalidFieldError


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

EXCLUDED_TYPES = {'user', 'bot'}
DATE_FORMATS   = ('%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d')
DIVISOR        = 86400
UNIT           = 'days'

PALETTE = {
    'age':    '#4C72B0',
    'surv':   '#DD8452',
    'ratio':  '#55A868',
    'kde':    '#C44E52',
    'median': '#8172B2',
}


# ══════════════════════════════════════════════════════════════════════════════
# STRUCTURES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ParseStats:
    total:        int = 0
    parse_err:    int = 0
    type_skip:    int = 0
    no_ban:       int = 0
    no_dates:     int = 0
    neg_age:      int = 0   # discovered < created: data anomaly
    neg_survival: int = 0   # banned <= discovered

    @property
    def qualified(self) -> int:
        return (self.total
                - self.parse_err
                - self.type_skip
                - self.no_ban
                - self.no_dates
                - self.neg_age
                - self.neg_survival)

    def print_summary(self, folder: Path):
        print(f"\n{'═' * 54}")
        print("  BAN TIMELINE ANALYSIS")
        print(f"{'═' * 54}")
        print(f"  Folder                         : {folder}")
        print(f"  .md files                      : {self.total}")
        print(f"  Parsing errors                 : {self.parse_err}")
        print(f"  Excluded (user/bot)            : {self.type_skip}")
        print(f"  Status != banned               : {self.no_ban}")
        print(f"  Missing dates                  : {self.no_dates}")
        print(f"  Anomalies (discovered<created) : {self.neg_age}")
        print(f"  Survival ≤ 0                   : {self.neg_survival}")
        print(f"  {'─' * 46}")
        print(f"  Qualified entities             : {self.qualified}")
        print(f"{'═' * 54}\n")


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def get_field_date(entity: TelegramEntity, field_name: str) -> datetime | None:
    """
    Extracts the date from a simple inline field (created, discovered…).
    Two cases:
      - datetime_obj populated  → date after comma: `val, 2026-01-17`
      - datetime_obj None       → the date IS the value: `2022-03-24`
    """
    fv = entity.doc.get_value(field_name)
    if not fv:
        return None
    if fv.datetime_obj:
        return fv.datetime_obj
    raw = fv.value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


# ══════════════════════════════════════════════════════════════════════════════
# VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

def validate_entity(entity: TelegramEntity, stats: ParseStats) -> dict | None:
    """
    Validates an entity and returns a data dict if qualified,
    None otherwise. Updates stats counters accordingly.
    """
    try:
        etype = entity.get_type()
    except (MissingFieldError, InvalidFieldError):
        stats.type_skip += 1
        return None

    if etype in EXCLUDED_TYPES:
        stats.type_skip += 1
        return None

    status_obj = entity.get_status(allow_strikethrough=False)
    if not status_obj or status_obj.value != 'banned' or status_obj.date is None:
        stats.no_ban += 1
        return None

    banned_dt      = status_obj.date
    created        = get_field_date(entity, 'created')
    discovered_raw = get_field_date(entity, 'discovered')
    discovered     = discovered_raw or get_field_date(entity, 'joined')
    discovered_src = 'discovered' if discovered_raw else 'joined'

    if not (created and discovered):
        stats.no_dates += 1
        return None

    age_at_discovery = (discovered - created).total_seconds() / DIVISOR
    survival         = (banned_dt  - discovered).total_seconds() / DIVISOR

    if age_at_discovery < 0:
        stats.neg_age += 1
        return None

    if survival <= 0:
        stats.neg_survival += 1
        return None

    life_total      = age_at_discovery + survival
    pct_life_before = age_at_discovery / life_total * 100

    return {
        'file':             entity.file_path.name,
        'type':             etype,
        'age_at_discovery': age_at_discovery,
        'survival':         survival,
        'ratio':            age_at_discovery / survival,
        'pct_life_before':  pct_life_before,
        'discovered_ts':    discovered.timestamp(),
        'discovered_src':   discovered_src,
    }


# ══════════════════════════════════════════════════════════════════════════════
# VISUALISATION
# ══════════════════════════════════════════════════════════════════════════════

def _plot_hist(ax, data, title, xlabel, color, bins):
    arr = np.array(data)
    ax.hist(arr, bins=bins, color=color, alpha=0.75, edgecolor='white', linewidth=0.6)

    if len(arr) > 1 and arr.std() > 0:
        kde_x = np.linspace(arr.min(), arr.max(), 300)
        kde_y = gaussian_kde(arr)(kde_x)
        ax.plot(kde_x, kde_y * len(arr) * (arr.max() - arr.min()) / bins,
                color=PALETTE['kde'], linewidth=1.8, label='KDE')

    med, avg = np.median(arr), np.mean(arr)
    ax.axvline(med, color=PALETTE['median'], linestyle='--', linewidth=1.5,
               label=f'Median: {med:.1f}')
    ax.axvline(avg, color='black', linestyle=':', linewidth=1.3,
               label=f'Mean: {avg:.1f}')

    ax.set_title(title, fontsize=11, fontweight='bold')
    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_ylabel("Entity count", fontsize=9)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.legend(fontsize=8)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)


def plot(df: pd.DataFrame, bins: int, out_path: Path):
    n        = len(df)
    med_age  = df['age_at_discovery'].median()
    med_surv = df['survival'].median()

    YEARS = 365.25
    MONTHS = 30.44
    age_years = df['age_at_discovery'] / YEARS

    fig = plt.figure(figsize=(16, 13))
    fig.suptitle(f"Ban Timeline Analysis  —  {n} entities",
                 fontsize=15, fontweight='bold', y=0.98)
    gs = gridspec.GridSpec(2, 3, figure=fig, hspace=0.45, wspace=0.35)

    ax1 = fig.add_subplot(gs[0, 0])
    _plot_hist(ax1, age_years,
               'Age at discovery\n(created → discovered)',
               'years', PALETTE['age'], bins)
    # Secondary axis in months
    ax1_months = ax1.secondary_xaxis('top', functions=(
        lambda y: y * YEARS / MONTHS,
        lambda m: m * MONTHS / YEARS
    ))
    ax1_months.set_xlabel('months', fontsize=8)

    ax2 = fig.add_subplot(gs[0, 1])
    _plot_hist(ax2, df['survival'],
               'Post-discovery survival\n(discovered → banned)',
               UNIT, PALETTE['surv'], bins)

    ax3 = fig.add_subplot(gs[0, 2])
    _plot_hist(ax3, df['pct_life_before'],
               'Life elapsed at discovery\n(% of total lifespan)', '%',
               PALETTE['ratio'], bins)

    # Scatter avec quadrants
    ax4 = fig.add_subplot(gs[1, 0:2])
    type_palette = plt.cm.tab10.colors
    for i, (etype, group) in enumerate(df.groupby('type')):
        ax4.scatter(group['age_at_discovery'] / YEARS, group['survival'],
                    label=etype, alpha=0.7, s=60,
                    color=type_palette[i % 10], edgecolors='white', linewidth=0.5)

    ax4.axvline(med_age / YEARS, color='grey', linestyle='--', linewidth=1.0, alpha=0.7)
    ax4.axhline(med_surv, color='grey', linestyle='--', linewidth=1.0, alpha=0.7)

    # Annotation directly in the strong-signal quadrant (bottom-right)
    ax4.text(0.99, 0.01,
             'strong signal\n(age ↑, survival ↓)',
             transform=ax4.transAxes,
             ha='right', va='bottom', fontsize=8,
             color='#C44E52', fontstyle='italic',
             bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.6, edgecolor='#C44E52'))

    ax4.set_xlabel('Age at discovery (years)', fontsize=9)
    ax4.set_ylabel(f'Post-discovery survival ({UNIT})', fontsize=9)
    ax4_months = ax4.secondary_xaxis('top', functions=(
        lambda y: y * YEARS / MONTHS,
        lambda m: m * MONTHS / YEARS
    ))
    ax4_months.set_xlabel('months', fontsize=8)
    ax4.set_title('Quadrants: age at discovery vs survival\n'
                  '(lines = medians)', fontsize=10, fontweight='bold')
    ax4.legend(fontsize=8, title='Type')
    ax4.spines['top'].set_visible(False)
    ax4.spines['right'].set_visible(False)

    # Boxplots
    ax5 = fig.add_subplot(gs[1, 2])
    bp = ax5.boxplot(
        [age_years.values, df['survival'].values],
        tick_labels=['Age\n(years)', f'Survival\n({UNIT})'],
        patch_artist=True,
        medianprops=dict(color='black', linewidth=2)
    )
    bp['boxes'][0].set_facecolor(PALETTE['age'])
    bp['boxes'][1].set_facecolor(PALETTE['surv'])
    for patch in bp['boxes']:
        patch.set_alpha(0.75)
    ax5.set_title('Comparative boxplots', fontsize=11, fontweight='bold')
    ax5.spines['top'].set_visible(False)
    ax5.spines['right'].set_visible(False)

    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    print(f"  Chart saved: {out_path}")
    plt.show()


# ══════════════════════════════════════════════════════════════════════════════
# INTERPRETIVE ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def print_analysis(df: pd.DataFrame):
    age  = df['age_at_discovery'].values
    surv = df['survival'].values
    rat  = df['ratio'].values
    plb  = df['pct_life_before'].values
    n    = len(df)

    med_age   = np.median(age)
    med_surv  = np.median(surv)
    med_ratio = np.median(rat)
    med_plb   = np.median(plb)

    pct_1d  = (surv <  1).mean() * 100
    pct_7d  = (surv <  7).mean() * 100
    pct_30d = (surv < 30).mean() * 100

    pct_ratio_3  = (rat >  3).mean() * 100
    pct_ratio_10 = (rat > 10).mean() * 100

    # Age ↔ survival correlation only.
    # ρ date/survival is shown for information but biased by censoring:
    # recent entities mechanically cannot have a long survival.
    rho_age,  pval_age  = spearmanr(age,                        surv)
    rho_disc, pval_disc = spearmanr(df['discovered_ts'].values, surv)

    # Quadrants (informational only — their symmetry is mathematically
    # guaranteed by the median cutoff, do not draw conclusions from it)
    q_strong = ((age >= med_age) & (surv <= med_surv)).sum()
    q_weak   = ((age <  med_age) & (surv <= med_surv)).sum()
    q_null_a = ((age >= med_age) & (surv >  med_surv)).sum()
    q_null_b = ((age <  med_age) & (surv >  med_surv)).sum()

    def sig_label(p):
        if p < 0.001: return "p < 0.001  ***"
        if p < 0.01:  return "p < 0.01   **"
        if p < 0.05:  return "p < 0.05   *"
        return         f"p = {p:.3f}   ns"

    print(f"{'═' * 60}")
    print("  ANALYSIS — Does discovery influence the ban?")
    print(f"{'═' * 60}")

    print(f"\n  Post-discovery survival (discovered → banned)")
    print(f"    Median           : {med_surv:.1f} days")
    print(f"    Banned in < 1d   : {pct_1d:.1f}%")
    print(f"    Banned in < 7d   : {pct_7d:.1f}%")
    print(f"    Banned in < 30d  : {pct_30d:.1f}%")

    print(f"\n  Discovery position in entity lifespan")
    print(f"    Median: {med_plb:.0f}% of lifespan elapsed at discovery")
    print(f"    → On median, only {100 - med_plb:.0f}% of lifespan remained after discovery")

    print(f"\n  Age/survival ratio  (technical)")
    print(f"    Median           : {med_ratio:.1f}x")
    print(f"    Ratio > 3x       : {pct_ratio_3:.1f}%  of entities")
    print(f"    Ratio > 10x      : {pct_ratio_10:.1f}%  of entities")

    print(f"\n  Spearman correlations  (n={n})")
    print(f"    {'Variable':<35} {'ρ':>7}   Significance")
    print(f"    {'─' * 58}")
    print(f"    {'Age at discovery  ↔  survival':<35} {rho_age:>+7.3f}   {sig_label(pval_age)}")
    print(f"    {'Discovery date    ↔  survival':<35} {rho_disc:>+7.3f}   {sig_label(pval_disc)}")
    print(f"    (ρ date/survival biased by censoring — do not interpret directly)")

    print(f"\n  Quadrants  (thresholds: median age={med_age:.0f}d, median survival={med_surv:.0f}d)")
    print(f"    (note: count symmetry is a mathematical property")
    print(f"     of the median cutoff, not a result)")
    print(f"    ┌──────────────────────────────┬───────────────────────────┐")
    print(f"    │ High age + short survival    │ High age + long survival  │")
    print(f"    │  → STRONG SIGNAL      {q_strong:>4}   │  → No signal         {q_null_a:>4} │")
    print(f"    ├──────────────────────────────┼───────────────────────────┤")
    print(f"    │ Low age + short survival     │ Low age + long survival   │")
    print(f"    │  → Weak signal        {q_weak:>4}   │  → No signal         {q_null_b:>4} │")
    print(f"    └──────────────────────────────┴───────────────────────────┘")

    print(f"\n  Conclusion")
    # Main reasoning: if entities had already lived the vast majority
    # of their lifespan before being discovered, AND are banned quickly
    # afterwards, then discovery is very likely the ban trigger —
    # they existed without being banned, and the ban follows shortly after.
    if med_age >= 30 and pct_30d >= 90:
        strength = "Strong"
        msg = (
            f"Entities had existed for {med_age:.0f} days on median without being banned,\n"
            f"    and {pct_30d:.0f}% were banned within 30 days of discovery\n"
            f"    (median: {med_surv:.1f} days). Entities that were evading Telegram\n"
            f"    and are banned in the days following discovery —\n"
            f"    discovery is very likely the ban trigger."
        )
    elif med_age >= 14 and pct_30d >= 75:
        strength = "Moderate"
        msg = (
            f"Entities had existed for {med_age:.0f} days on median before discovery,\n"
            f"    and {pct_30d:.0f}% were banned within the following 30 days.\n"
            f"    Signal present but not concentrated enough for a firm conclusion."
        )
    elif pval_age < 0.05 and rho_age < 0:
        strength = "Moderate"
        msg = (
            f"Significant negative age/survival correlation (ρ={rho_age:+.2f}):\n"
            f"    older entities are banned faster after discovery.\n"
            f"    Discovery could be a trigger, especially for\n"
            f"    the oldest entities."
        )
    else:
        strength = "Weak"
        msg = (
            f"No clear signal. Entities had existed for {med_age:.0f} days\n"
            f"    on median before discovery, but post-discovery survival\n"
            f"    is too variable to conclude a triggering effect.\n"
            f"    Telegram likely bans according to its own mechanisms,\n"
            f"    independently of discovery."
        )

    print(f"    [{strength}] {msg}")
    print(f"\n{'═' * 60}\n")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def analyse(folder: Path, bins: int = 10):
    md_files = sorted(folder.glob('*.md'))
    if not md_files:
        print(f"No .md files found in {folder}", file=sys.stderr)
        sys.exit(1)

    stats         = ParseStats()
    stats.total   = len(md_files)
    records       = []

    for path in md_files:
        try:
            entity = TelegramEntity.from_file(path)
        except Exception as e:
            print(f"  [WARN] {path.name}: parsing error — {e}", file=sys.stderr)
            stats.parse_err += 1
            continue

        record = validate_entity(entity, stats)
        if record:
            records.append(record)

    stats.print_summary(folder)

    if not records:
        print("  No qualified entities.\n")
        return

    df = pd.DataFrame(records)

    stats_df = df[['age_at_discovery', 'survival', 'pct_life_before']].describe().loc[
        ['mean', '50%', 'std', 'min', 'max', 'count']
    ]
    stats_df.index   = ['Mean', 'Median', 'Std dev', 'Min', 'Max', 'N']
    stats_df.columns = ['Age at discovery (d)', 'Post-discovery survival (d)', 'Life elapsed (%)']
    print(stats_df.to_string(float_format=lambda x: f"{x:.2f}"))
    print()

    print("Distribution by type:")
    print(df['type'].value_counts().to_string())
    print()

    print("Source of 'discovered' field:")
    print(df['discovered_src'].value_counts().to_string())
    print()

    print_analysis(df)
    plot(df, bins, folder / f'ban_timeline {datetime.now().strftime('%Y-%m-%d')} 📉.png')


def main():
    parser = argparse.ArgumentParser(
        description="Analysis of created→discovered→banned delays for Telegram MDML entities."
    )
    parser.add_argument('folder', help="Path to the folder containing .md files")
    parser.add_argument('--bins', type=int, default=10,
                        help="Number of bins for histograms (default: 10)")
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.is_dir():
        print(f"ERROR: '{folder}' is not a valid directory.", file=sys.stderr)
        sys.exit(1)

    analyse(folder, bins=args.bins)


if __name__ == '__main__':
    main()
