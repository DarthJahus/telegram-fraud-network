## Documentation Principles
- Documentation is link-driven.
- An entity is documented only if it is linked to an already known entity or consists of a new hub of activity
- Links reflect the direction of discovery.

## Minimal Information
Each entity file may contain:
- Telegram ID (or invitation link placeholder)
- type: `channel` | `group` | `user`
- functional Telegram link
- links to:
- owner / admin (if visible)
- bio and external links (if present)
- observed status (`active` | `banned` | `deleted`) with date

## Backups and Exposures
Backups are created only when necessary.

Typical cases include:
- unmasked personal data
- identity documents
- weapons / firearms
- explicit illegal instructions

For each backup:
- the backup folder is recorded

For each incident:
- the media file is noted
- a direct Telegram link to the source message is included:
(`t.me/c/<id>/<msg_id>`)

Backups are evidentiary, not archival.

## Status Tracking
Statuses reflect observation, not platform metadata.

- `active`: entity confirmed active at a given date (when checked)
- `banned`: entity observed as unavailable, with date of observation
- `deleted`: "Deleted User"

Exact ban dates are usually unknown and are not inferred.
