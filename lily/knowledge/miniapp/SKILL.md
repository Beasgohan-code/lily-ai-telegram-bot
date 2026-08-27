# Mini App Integration Skill

Lily’s Mini App is an administrative interface, not an authority bypass. A future live bridge must verify Telegram `initData` server-side with the bot token-derived signature, authorize the requesting user for the selected chat, and call a public HTTPS API. The deployed static interface must not claim live management before this bridge exists.

The Mini App may display group controls, queues, media jobs, skills, project status, and redacted diagnostics. Any privileged mutation must preserve the same administrator check, confirmation policy, source/repository allow-lists, and audit event as a Telegram chat action.
