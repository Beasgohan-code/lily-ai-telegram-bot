# Model Routing Skill

Lily’s configured provider order is **compatible free or self-hosted providers**, then **Gemini**, then **OpenAI-compatible primary profiles**, then **Groq**. Missing credentials skip a profile rather than causing an error. Provider health tracks failures, active probes, and cooldowns so rate-limit storms and repeated malformed responses do not repeatedly hit the same unavailable provider.

Anonymous/public providers are excluded unless the operator explicitly enables public fallback for content that is safe to share externally. Sensitive group context, private memories, credentials, and files must never be sent to those services by default. Lily reports concise provider availability but never provider keys or request bodies.
