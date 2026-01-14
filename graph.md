## Graph Construction
The graph emerges from observed relations:
- calls to action
- admin or owner visibility
- bio links
- invitation links
- forwards
- chat groups linked to channels (`discussion`/`linked channel`)

No inferred or speculative links are added.

## Directionality
All links are directional.

Links represent how an entity was discovered from another entity.
Reverse or inferred relationships are not added unless explicitly observed.

## Emergent Structure
The graph is not designed top-down.

It emerges from the accumulation of:
- manually written entity files
- explicit links created during observation
- persistent identifiers (Telegram IDs)

Hubs, recurrent actors, and sub-networks are not defined explicitly. They become visible through link density and directionality.

## Entity Type Evolution
Entities marked as `unknown` represent:
- accounts discovered through links but not yet visited
- entities whose type cannot be determined (suspended before observation)
- placeholder entries pending verification

Unknown entities may be reclassified upon observation.

## Post-Ban Observation
When a channel or group is banned:
- the ban is recorded with observation date
- no immediate conclusion is drawn
- related entities are observed over time

In practice, activity often resumes through:
- backup channels
- connected accounts
- direct user migration

## Analytical Use
The graph allows structural reading, including:
- identification of recurrent actors across multiple entities
- detection of operational sub-networks
- observation of isolation or fragmentation after bans
- comparison between reported entities and moderation outcomes
- temporal analysis of moderation effectiveness

All observations rely on documented links only.

### Temporal Analysis
The combination of `discovered`, `created`, and `status` timestamps enables:
- measurement of time between discovery/reporting and moderation action
- assessment of whether bans correlate with recent reporting
- distinction between pre-existing entities and newly created ones

These metrics do not prove causation but provide context for moderation patterns.
