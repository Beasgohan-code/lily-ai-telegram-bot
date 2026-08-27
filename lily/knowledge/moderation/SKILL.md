# Group Moderation Skill

Lily administers groups through natural language and persists policy in SQLite. It supports member governance, restrictions, warnings, pinned-message actions, filters, content locks, anti-spam thresholds, trusted members, domain blocks, join handling, verification, welcome/goodbye messages, reports, case notes, and audit exports.

Before a harmful or irreversible action, Lily identifies the exact reply target or numeric ID, confirms the requester is a group administrator, presents a bounded action plan, and waits for confirmation. Trusted-member status is an explicit persisted exemption, never an implicit AI guess. Warning escalation is bounded in duration and recorded whether or not Telegram accepts the restriction.

The `GROUP_CONTROLS` catalogue is the source of control names; handlers must not invent undocumented policy keys. Lily should offer the current policy status, recent audits, verification queue count, and open reports when an administrator requests group diagnostics.
