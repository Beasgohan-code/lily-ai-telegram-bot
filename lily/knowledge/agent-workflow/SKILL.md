# Agent Workflow Skill

Lily turns a natural-language request into one named action, validates required fields, checks chat and capability permissions, and either executes a safe action or requests confirmation. It shows a concise public stage list such as **validate**, **confirm**, **execute**, and **audit**. These are process labels only; Lily must never expose hidden chain-of-thought, private provider reasoning, API keys, or raw environment values.

Actions have three risk levels. Safe read-only actions may run after permission checks. Risky and dangerous actions require an owner-bound confirmation callback and expire after the configured TTL. Any missing target, file, source URL, permission, or rights claim stops execution and asks for the precise missing detail.

Every completed privileged action records an audit event. The action handler, not the model output, is the final authority for targets, capability gates, allow-lists, filesystem paths, source domains, and Telegram administrator status.
