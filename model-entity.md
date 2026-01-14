## Primary Entity: `telegram_account`
All documented entities are Telegram accounts or related infrastructure.

An entity can be one of:
- `channel`
- `group`
- `user`
- `bot`
- `website` (external infrastructure linked from Telegram)
- `unknown` (entity type not yet or can't be determined)

Each entity is identified primarily by its Telegram numeric `ID`.
Website entities are identified by `domain`.

Usernames (`@`), names, bios and invitation links are considered mutable
and secondary.

## Roles
When observable, additional roles may be noted:
- owner
- admin
- actor
- client (rare)

Roles are observations, not assumptions.
