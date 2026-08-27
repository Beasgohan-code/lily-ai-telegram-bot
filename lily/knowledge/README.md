# Lily Project Knowledge Library

This library contains the durable operating knowledge for Lily’s named skills. It is deliberately **curated and version-controlled**: skills describe approved procedures and safeguards; they do not grant an LLM raw shell access, unrestricted filesystem access, broad network retrieval, or authority to bypass confirmations.

| Skill area | Purpose |
|---|---|
| `moderation` | Group governance, 60+ controls, confirmation, auditing, and enforcement limits. |
| `media` | Rename, inspection, encoding, streaming, and direct-file safety checks. |
| `channels` | Drafting, approval, publishing, deletion, and post indexing. |
| `model-routing` | Free → Gemini → OpenAI → Groq priority and privacy-tier fallback. |
| `bot-operations` | Managed project records, allow-listed repositories, isolated environments, and dry-run provisioning. |
| `deployment` | Persistent-host topology, configuration, health, recovery, and logs. |
| `miniapp` | Authenticated Mini App integration boundaries. |
| `agent-workflow` | Public stages, plan validation, confirmation, execution, and audits. |

Each document provides a stable protocol that Lily’s AI planner can summarize, while actual authority remains in Python action handlers and host configuration.
