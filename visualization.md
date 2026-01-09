## Graph Representation

- The graph is a relational, directed graph.
- Nodes represent `telegram_account` entities, reports and incidents.
- Edges represent observed directional relationships.
- The graph is produced using Obsidian.

Visualization relies strictly on observed relationships.

No additional inference or weighting is applied during visualization.

### Color Coding
The following color scheme is used for visualization:

⬛️ banned channel or group  
⬛️ deleted user  
🟥 incidents (recognizable identities)  
🟩 reports (IC3, registrar, Telegram)  
🟦 hub  
🟪 activity: bank accounts  
🟨 activity: bank checks  
🟧 activity: firearms  
🟫 activity: investment scam  

Tags are not displayed directly on the graph.

## Visualization as Analysis
Visualization is not decorative.

It is used as a reading tool to:
- reveal structural patterns
- compare persistence over time
- observe the effects (or absence) of moderation actions

Interpretation is based on structure, not on visual aesthetics.

## Temporal Snapshots
Graph images are captured at different points in time.

These snapshots allow:
- observation of network persistence
- visualization of post-ban reconfiguration
- comparison of network structure before and after moderation actions
- visualization of moderation action propagation

---

Graph construction rules are defined in:
- [Graph Construction](graph.md)
