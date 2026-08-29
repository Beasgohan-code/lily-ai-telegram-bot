# Agency orchestration

Lily supports NEXUS-style scenario runbooks: phased teams, explicit deliverables,
and handoff cards between specialist roles. Scenarios do **not** grant new tools.

## Commands

- `Lily, list scenarios` — show available runbooks
- `Lily, start scenario startup-mvp` — activate a phased workflow
- `Lily, show handoff` — display the current plan's handoff card

## Phases

Each scenario walks through Discover → Build → Harden → Launch style phases.
Lily shows public stage labels only; private role memos never appear in chat.

## Safety

All scenario steps route through Lily's central Plan, permission checks, and
confirmation gates. Specialist roles can raise risk or flag missing details but
cannot change the action or execute tools independently.
