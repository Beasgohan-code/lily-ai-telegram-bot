# RAG routing

Lily routes natural-language requests to bundled operating knowledge collections
before planning. This improves grounding without exposing arbitrary filesystem access.

## Collections

| Collection | Topics |
|---|---|
| moderation | bans, filters, locks, reports |
| media | encode, rename, stream, FFmpeg |
| series-release | manga tracking, chapters |
| queue | background jobs, cancellation |
| channels | Rich posts, announcements |
| model-routing | providers, fallbacks, cooldowns |
| deployment | hosting, services, recovery |
| agent-workflow | plans, confirmations, audit |

## Diagnostics

Ask `Lily, diagnose knowledge` or `/ragdebug` for P01–P12 failure patterns when
answers drift, citations are missing, or the wrong skill is selected.

## Deep research

Use `Lily, deep research: <question>` for parallel scout waves with cited synthesis.
