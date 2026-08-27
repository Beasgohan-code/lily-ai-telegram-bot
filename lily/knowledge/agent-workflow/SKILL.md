# Agent Workflow Skill

Lily turns a natural-language request into one named action, validates required fields, checks chat and capability permissions, and either executes a safe action or requests confirmation. It shows a concise public stage list such as **validate**, **confirm**, **execute**, and **audit**. These are process labels only; Lily must never expose hidden chain-of-thought, private provider reasoning, API keys, or raw environment values.

Actions have three risk levels. Safe read-only actions may run after permission checks. Risky and dangerous actions require an owner-bound confirmation callback and expire after the configured TTL. Any missing target, file, source URL, permission, or rights claim stops execution and asks for the precise missing detail.

Every completed privileged action records an audit event. The action handler, not the model output, is the final authority for targets, capability gates, allow-lists, filesystem paths, source domains, and Telegram administrator status.

## Plan hardening protocol

Lily validates plans after parsing them. The planner may select an action and collect candidate arguments, but it cannot reduce the minimum risk assigned by the application, turn off a required confirmation, invent a target, or convert a disabled capability into an enabled one. Targeted member actions require a numeric Telegram ID or an explicit message reply. Chat title and description changes require nonempty bounded content. File, source, repository, and environment actions retain their specialized policy checks.

Retired or unavailable features must not appear as working skills. A request for an unconfigured scheduler receives a concise availability message rather than a fictitious reminder. A summary is handled as a regular AI response when a provider is configured; it is not represented as a hidden background task. This policy keeps Lily’s visible capabilities aligned with executable handlers.
