## Telegram Fraud Network
This repository documents a manual OSINT-based method to observe and
document fraud-related activity on Telegram.

The focus is not on automation or scraping, but on:
- persistent Telegram accounts (channels, groups, users)
- observable links between them
- the effects and limits of Telegram moderation actions

The repository also provides a reproducible documentation method
that can be used by researchers, journalists, or investigators.

## Info
### Project Timeline
- **Start date**: December 21, 2025
- **Observation method**: Manual OSINT, no automation
- **Current scope**: See statistics for (reasonably) up-to-date metrics

### Statistics
```vb
──────────────────────────────────────────────────────────────────────
📊 GLOBAL OVERVIEW
──────────────────────────────────────────────────────────────────────
📄 Total entries        :  863
🔨 Banned               :    -     -%
🗑️ Deleted              :    -     -%
❓ Unknown              :    -
🟢 Active               :    -     -%
🟢 Active non users     :  181     -%

──────────────────────────────────────────────────────────────────────
🧩 ENTRY TYPES
──────────────────────────────────────────────────────────────────────
Channel   : 275 •    - 🟢     -% •    - ❓     -% •    - 🔨     -%
Group     :  85 •    - 🟢     -% •    - ❓     -% •    - 🔨     -%
User      : 426 •    - 🟢     -% •    - ❓     -% •    - 🗑️     -%
Bot       :  36 •    - 🟢     -%                  •    - 🗑️     -%
Unknown   :  41 •    - 🟢     -% •    - ❓     -% •    - 🔨     -%

──────────────────────────────────────────────────────────────────────
🏷️  TAG ANALYSIS
──────────────────────────────────────────────────────────────────────
 TAG                 TOTAL       %  ACTIVE       %
 ──────────────────  ─────   ─────  ──────   ─────
 💳 FINANCIAL FRAUD
  #bankaccounts          -      -%       -      -%
  #checking              -      -%       -      -%
  #carding               -      -%       -      -%

 ⛏ CRYPTO / SCAMS
  #crypto                -      -%       -      -%
  #investment_scam       -      -%       -      -%

 🧰 INFRA / NOISE
  #hub                   -      -%       -      -%
  #backup                -      -%       -      -%

 📦 OTHER TAGS
  #spam                  -      -%       -      -%
  #bot                   -      -%       -      -%
  #fake_documents        -      -%       -      -%
  #drugs                 -      -%       -      -%
  #money                 -      -%       -      -%
```

## Repository Structure and Method Overview
This repository is organized around a documented observation workflow.

### Core Method
- [Method](method.md) — documentation principles and entity modeling
- [Actions](actions.md) — actions taken after observation
- [Ethics](ethics.md) — ethical boundaries and non-assumptions
- [Scope](scope.md) — explicit inclusion and exclusion criteria

### Graph and Analysis
- [Graph Construction](graph.md) — how relationships are observed and recorded
- [Visualization](visualization.md) — graph representation and color coding
- [Moderation Observations](moderation.md) — observed platform behavior

### Harm and Reporting
- [Incidents](incidents.md) — documentation of victim exposure
- [Reports](reports.md) — external reporting actions

This structure reflects the separation between:
- observation
- documentation
- action

## Contributing
Feedback on methodology is welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Pull requests for documentation improvements are accepted.

For discussions, use the [Discussions](https://github.com/DarthJahus/telegram-fraud-network/discussions) tab.

## Citation
If you use this methodology in your research, please cite this repository. 

See [CITATION.cff](CITATION.cff) or use GitHub's "Cite this repository" button.
