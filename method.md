## Documentation Principles
- Documentation is link-driven.
- An entity is documented only if it is linked to an already known entity or consists of a new hub of activity
- Links reflect the direction of discovery.

## Minimal Information
Each [[entity_tg|entity]] may contain:
- Telegram ID (or invitation link placeholder)
- type: `channel` | `group` | `user` | `bot` | `website`
- discovered: date and time when the entity was first observed
- functional Telegram link
- links to:
- owner / admin (if visible)
- bio and external links (if present)
- observed status (`active` | `banned` | `deleted`) with date
- creation date (if possible)
- join date

## Backups and Exposures
Backups are created only when necessary.

Typical cases include:
- **Incidents**: unmasked personal data or identity documents (when victim is identifiable)
- **Pre-migration signals**: entity preparing to delete content or migrate
- **High-severity content**: weapons/firearms, explicit illegal instructions

For each backup:
- the backup folder is recorded with date
- reason for backup is noted

For each incident:
- the media file is noted
- a direct Telegram link to the source message is included:
  (`t.me/c/<id>/<msg_id>`)
- victim identifiability is assessed

Backups are evidentiary, not archival.

## Status Tracking
Statuses reflect observation, not platform metadata.

- `active`: entity confirmed active at a given date and time (when checked)
- `banned`: entity observed as unavailable, with date and time of observation
- `deleted`: Deleted User or Bot, with date and time of observation

Exact ban dates are usually unknown and are not inferred.

The `discovered` timestamp typically coincides with reporting, as entities are reported immediately upon discovery. Combined with `created` and `status` dates, this enables rough assessment of moderation response times.

---

This documentation method directly produces a graph.

See:
- [Graph Construction](graph.md)
- [Visualization](visualization.md)
- Tool: [[/tools/telegram_checker/README|Telegram Status Checker]]
