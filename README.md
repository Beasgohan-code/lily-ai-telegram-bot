# Lily — AI-first Telegram backend

Lily is a Python backend for an AI-first Telegram assistant and group manager. It uses `python-telegram-bot` for updates and standard Telegram actions, while calling the new RichMessage methods through a small raw HTTP client because the current typed PTB release may not expose every newest rich-message type yet.

## What is implemented

Lily accepts ordinary language instead of requiring a command-driven workflow. A private message or a group mention such as `Lily, ban this user` is converted into a strict action plan. Group moderation, file transformations, and other risky operations are routed through permission checks and confirmation cards with Yes, No, and Details buttons.

The backend includes per-user and per-chat daily and monthly request quotas, daily and monthly byte quotas, SQLite persistence, pending-action expiration, audit logs, custom trigger skills, RichMessage headings/tables/quotations/details, private rich draft progress when supported, document creation in TXT/Markdown/JSON/CSV/HTML/PDF, safe file renaming, ZIP compression, FFmpeg encoding, a rights-respecting direct-audio downloader, fallback AI-key rotation, a channel-post studio, paginated media-search result cards, and a persistent encoding queue manager.

The audio downloader intentionally does **not** scrape or rip streaming platforms. It accepts direct audio URLs only when the administrator explicitly enables downloads and configures an allow-list. Use it only for material you own, have permission to download, or that is legally available for download.

## Current limitations and extension points

Mira-style external integrations, proactive reminders, image generation, deep web research, and advanced memory retrieval are represented as safe router actions and extension points, but they require provider-specific connectors. The core intentionally refuses to claim that such an action completed until an integration is implemented. Lily’s built-in post search indexes posts that Lily publishes itself; searching arbitrary historical channel messages requires an additional authorized Telegram user-session connector and is intentionally not enabled by default.

The new Telegram rich-message methods are called through raw HTTP. This is deliberate: as of the current documentation review, the stable PTB API has local-server support, but the upstream rich-message typed support was still tracked separately. Lily sends RichMessage blocks directly and falls back to HTML `sendMessage` if the local Bot API server does not support RichMessage yet.

## Install

```bash
cd /home/ubuntu/lily
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Load the `.env` values using your preferred process manager or export them in the shell. Never commit `.env` or a bot token to Git.

## Local Bot API server

For near-1-GB files, run Telegram’s official Local Bot API Server on the same machine or a private network endpoint. The official API documentation states that the local server can download files without a size limit and upload files up to 2000 MB. Lily therefore defaults to:

```text
TELEGRAM_API_BASE=http://127.0.0.1:8081/bot
TELEGRAM_FILE_BASE=http://127.0.0.1:8081/file/bot
TELEGRAM_LOCAL_MODE=true
```

The local server requires Telegram API credentials (`api_id` and `api_hash`) and a persistent data directory. Follow the official Local Bot API Server build and run instructions for the current binary/container method. Do not expose the local Bot API server directly to the public internet; place it behind a private network or authenticated reverse proxy.

For a lightweight development run without a local server, set `TELEGRAM_LOCAL_MODE=false` and leave the default Telegram API URLs in place. Large-file guarantees then do not apply.

## AI provider

Lily uses an OpenAI-compatible chat-completions endpoint. Set `OPENAI_API_KEY`, `OPENAI_API_BASE`, and `LILY_AI_MODEL`. The default model is `gpt-5-mini`; the router requests strict JSON-schema output and low reasoning effort for intent planning. The code shows progress stages such as “Checking permissions” and “Preparing compression”; it does not expose private chain-of-thought.

For fallback support, set `LILY_AI_KEYS` to a comma-separated list of keys. Set `LILY_AI_BASES` to the matching comma-separated list of API bases, or provide one base that will be reused for all keys. Lily moves to the next provider after authentication, rate-limit, timeout, conflict, malformed-response, or server errors. It reserves one in-flight health probe per profile, so a burst of user messages does not repeat an initial rate-limited request before the cooldown is published.

For advanced multi-model routing, set `LILY_AI_PROFILES_JSON`. Each profile may define `name`, `api_key`, `base_url`, `model`, `family`, `capabilities`, `priority`, and `max_retries`. Lily selects only profiles supporting the requested capability, converts reasoning and token parameters for GPT, Claude, and Gemini families, records success/failure latency, and temporarily cools down unhealthy profiles. `model_status` can report current health in chat.

### Curated free-tier and local presets

Set `LILY_AI_PRESETS=all` to expose every catalogued provider for which the needed runtime credential is present. Set `LILY_ENABLE_ALL_CATALOG_MODELS=true` only when you intentionally want every listed model registered as a fallback candidate. Lily applies `LILY_FALLBACK_ORDER=free,gemini,openai,groq` across preset and explicit profiles: compatible free/self-hosted profiles are tried first, then Gemini, OpenAI-compatible primary profiles, and finally Groq. Profiles within a tier preserve their configured order.

The vendored CC0 catalog covers Aion Labs, Cohere, Gemini, Mistral, Z AI, Cloudflare Workers AI, Groq, Hugging Face, Kilo, LLM7, ModelScope, NVIDIA NIM, Ollama Cloud, OpenRouter, OVHcloud, SiliconFlow, and local Ollama. Cohere, Gemini, and Cloudflare use native adapter families; compatible providers use Lily’s OpenAI-style router. `LILY_ALLOW_PUBLIC_AI_FALLBACKS=false` blocks public or anonymous profiles by default, so Kilo, LLM7, OpenRouter free routing, and OVH anonymous mode cannot receive group memory, files, moderation evidence, or other sensitive context until an administrator deliberately opts in.

## Search pagination and encoding queue

Search results are stored in short-lived, owner-bound pagination sessions. Lily renders a page of results with previous, next, refresh, and close buttons, and rejects button presses from other users. Encoding jobs are persisted in SQLite with queued, running, completed, failed, and cancelled states. After approval, an encode request enters the background queue and receives refresh/cancel controls. A cancelled queued job is skipped before the worker starts it; a running job’s task is cancelled and its state is recorded.

## AI-first group controls

Lily now ships a **60-control group-management catalogue** that an admin operates in normal language. The categories cover member governance, member moderation, content locks, anti-spam, rules and automations, and privacy/intelligence. Examples include: “Enable caps control”, “Disable forward lock”, “Trust this member”, “Block domain example.com”, “Show group controls”, “Show open reports”, “Resolve report 12”, and “Approve join request for 123456789”. Member-affecting actions, policy changes, mass deletion, and join decisions remain confirmation-gated and Lily also checks its own Telegram rights before execution.

The current live policy engine enforces locks, forwarded-message restrictions, blocked domains, duplicate text, caps spam, excessive mentions, invite-link and emoji limits, suspicious-text reporting, media flooding, new-member cooldown and limits, filters, flood control, trusted-member exemptions, configurable warning escalation, reports, case notes, member verification, welcome/goodbye flows, and audit events. Scheduled posts, recurring summaries, and inactivity alerts remain persisted controls awaiting an always-on scheduler.

## Expanded agent tools

Lily now supports richer Rose-style operations through ordinary language: promote, demote, ban, unban, kick, mute, temporary text-only or read-only restrictions, restore permissions, warn, inspect and clear warnings, configure a bounded warning-to-restriction escalation, pin and unpin, purge, filters, locks, rules, welcome/goodbye configuration, member verification, trusted members, domain blocks, reports, private moderator case notes, polls, and group diagnostics. A confirmation gate remains mandatory for risky changes. The promotion profile intentionally omits promotion rights, so a newly promoted moderator cannot promote other accounts. The `auto_rename_enabled` and `auto_rename_template` chat settings can rename bare uploads automatically; source extensions are preserved and invalid filename characters are removed.

For streaming, reply to a Lily-managed file and ask for a direct streaming link. Lily downloads the file to managed storage, generates an expiring HMAC-signed URL, and exposes it through the optional FastAPI stream service. Set `LILY_STREAM_PUBLIC_BASE_URL` to an HTTPS reverse-proxy URL before enabling this feature. Do not expose the stream port directly to the internet or use it for files outside Lily’s managed work/download directories.

For web search, Lily uses the configured search endpoint and returns rich result tables plus expandable snippets. The default is DuckDuckGo’s Instant Answer endpoint; configure an alternative compatible provider if you need broader coverage.

## Image and video generation

Lily has provider-neutral image and video generation adapters. Set `LILY_IMAGE_GENERATION_URL` or `LILY_VIDEO_GENERATION_URL` and the matching API key for an authorized provider. Each endpoint receives a `prompt`, `aspect_ratio`, and `kind`; video requests also receive `duration_seconds`. The provider must return a top-level `url`, `output_url`, `image_url`, or `video_url` (or an equivalent first item under `data`/`outputs`). Lily asks for confirmation before a generation request so configured providers are not used accidentally.

## Agent CLI

The same model-aware Lily agent can be used from a terminal after configuration:

```bash
python3 -m lily.cli status
python3 -m lily.cli plan "Lily, demote user 12345"
python3 -m lily.cli ask "Draft a calm moderation message about spam links"
```

The CLI uses Lily’s configured multi-model fallback router and prints either model health, a strict action plan, or a conversational answer. It does not bypass Telegram permissions; use it for review, debugging, and offline drafting. The Ubuntu console includes `skill-match <chat_id> <user_id> <text>` to preview whether a custom automatic skill or the LLM planner would handle a request, and `skill-runs <chat_id> --user-id <id>` to list redacted outcomes. Neither command executes a Telegram action.

## Telegram Mini App

The optional `lily-miniapp/` project is a polished Telegram Web App dashboard for live agent activity, moderation controls, skills, media queues, search, and channel-post preparation. It currently ships as an interface-first companion and reads Telegram’s Web App client script; connecting it to Lily’s live database requires an authenticated backend bridge that verifies Telegram `initData` and exposes only the requesting admin’s group data. Do not trust Mini App client input without that server-side verification.

## Recommended next advanced features

| Feature | Why it matters |
|---|---|
| Admin review inbox | Gives every filter hit, report, and AI recommendation one consistent approval place. |
| Human moderation handoff | Lets Lily create a structured case file with context when it is uncertain rather than guessing. |
| Per-skill budget policies | Limits expensive generation, search, and media jobs by group, role, day, and month. |
| Semantic memory search | Retrieves prior rules, decisions, and post drafts by meaning, not only keywords. |
| Channel calendar | Schedules post drafts, approval windows, and recurring reports in one timeline. |
| Media library | Indexes Lily-generated links and uploaded content with expiration, access, and retention controls. |

## Custom skill plugins

Trusted local plugins live in the `plugins/` directory. Each plugin defines a `PLUGIN` manifest with a name, version, description, trigger list, an allow-listed Lily action, risk level, and optional `build_plan(context)` function. A plugin receives text and IDs, not a Telegram Bot object, so all Telegram operations still pass through Lily’s permission and confirmation layer. The included `plugins/hello_skill.py` is a safe example. Do not load untrusted plugin files; Python plugins can execute arbitrary code by design.

## Automatic custom skills

Database-backed custom skills can react to message keywords or explicitly supplied regular expressions. Each skill has an enabled state, priority, bounded cooldown, and execution mode. The default **suggest** mode displays a confirmation-required plan. Only the fixed safe reply action (`plugin_reply`) may use **auto** mode with `confirmation: never`. Moderation, media, downloads, code workspaces, group configuration, and channel publishing remain approval-gated even if a skill is accidentally configured for automatic operation.

Lily records a compact lifecycle record for every selected automatic skill: awaiting confirmation, approved, completed, cancelled, denied, failed, or needs-details. It stores public action names and short status labels only—not model reasoning, source-file metadata, environment values, or raw command strings. Ask `Lily, skill status` to see recent automatic-skill activity in the current chat.

## Channel Post Studio

An admin can say `Lily, create an anime episode announcement`. Lily asks what kind of post to create, asks for the destination channel ID or username, verifies that the requester is authorized and that Lily is an administrator with posting permission, looks up public anime metadata from AniList, renders the announcement with rich text and an expandable synopsis, shows a preview, and asks for final publication confirmation. The template includes primary-style RichMessage buttons. Lily stores the last published message ID per channel so an admin can later say `Lily, delete the last post in this channel`; deletion is also confirmed before execution.

## Start Lily

```bash
cd /home/ubuntu/lily
. .venv/bin/activate
set -a && . ./.env && set +a
python -m lily.main
```

For production, run Lily under a supervisor such as systemd or another process manager with automatic restart. Long polling is convenient for development. A webhook endpoint can be added later if the deployment exposes HTTPS.

## Large file workflow

When a user replies to a file and asks Lily to rename, compress, or encode it, Lily downloads it through the configured Bot API file endpoint, checks the configured limits, records byte usage, processes it in the work directory, uploads the result, and removes temporary files. The job semaphore limits concurrent transformations. Ensure the host has enough free disk for both the input and output; compression and transcoding can require more than twice the source-file size.

## Natural-language examples

```text
Lily, rename this file to My Movie - 2026 - 1080p.
Lily, compress this archive and send it back.
Lily, encode this video to H.264 MP4.
Lily, create a PDF report from this text.
Lily, ban this user for repeated scam links.
Lily, restrict user 123456789 to text only for one hour.
Lily, set the welcome message to Read the rules, {user}.
Lily, enable member verification for new members.
Lily, add a case note for report 7 saying review a repeated violation.
Lily, create a skill: when someone says “drop the link”, ask an admin before deleting the message.
Lily, register bot manga-bot from https://github.com/example/manga-bot with python-main entrypoint bot.py.
Lily, show custom run command options.
Lily, provision bot manga-bot.
Lily, track manhwa Solo Leveling at chapter 210.
Lily, list tracked series.
Lily, update Solo Leveling to chapter 211.
```

The user should reply directly to a target message or file when Lily needs an unambiguous target. This prevents the AI from guessing which member or file the user meant.

## Series release tracker

Lily includes an admin-managed **manual release tracker** for manga, manhwa, and manhua titles. It can normalize titles, record a known chapter, list active tracked series, preserve an audit trail, and help prepare a channel announcement from confirmed information. The tracker intentionally does not scrape third-party sites, mirror protected chapter pages, or download copyrighted chapter files. Those activities need separate rights, source agreements, and compliance review.

## Security checklist

Use a separate bot token for development, set restrictive filesystem permissions on `data`, `work`, and `downloads`, configure disk quotas, keep the Bot API server private, run the process as a non-root user, and review audit logs. Do not enable direct audio downloads without an allow-list. Do not let custom skills contain arbitrary shell commands; skills are restricted to named backend actions.

## Managed bot registry and environment wizard

Lily includes a **managed-project foundation** for operators who want to run approved bot repositories from one controlled host. It stores the project slug, HTTPS GitHub repository, branch, runtime, fixed run profile, target entrypoint or module, isolated project root, host-only environment path, owner, status, revision, and errors in SQLite. The current supported runtime options are `python-main`, `python-module`, `node-start`, and `docker-compose-up`; Lily does not accept an arbitrary command pasted into chat.

The environment wizard parses a project’s `.env.example`, recognizes likely secret names, validates common URL, integer, and boolean values, and writes a generated host-only `.env` by atomic replacement with mode `0600`. It provides only a redacted status view, so tokens and passwords never appear in audit logs or chat replies. Secret collection must occur through a private authenticated surface, not in a group chat.

Set `LILY_ALLOWED_PROJECT_REPOSITORIES` to a comma-separated exact HTTPS GitHub allow-list before registering projects. `LILY_BOT_FACTORY_DRY_RUN=true` is the default and ensures that a provision request displays the exact fixed clone, install, and run plan without changing the host. Set it to `false` only after the always-on host, test bot, service supervisor, storage, and secret handling are verified. In active mode, Python projects can install from `requirements.txt` with `python -m pip install --no-input -r requirements.txt` or from `pyproject.toml`; Node and Docker Compose projects use fixed reviewed plans. Dependency installation can run third-party code, so a repository approval and confirmation remain mandatory.

## Curated operating skills and multi-step execution

Lily includes a version-controlled project-knowledge library in `lily/knowledge/`. It provides focused `SKILL.md` playbooks for agent workflow, moderation, media, channels, model routing, bot operations, deployment, and Mini App integration. These guides define safe procedures for named Python actions; they do not grant models arbitrary shell commands, unrestricted filesystem access, or the ability to add tools dynamically.

For every named action, Lily can show a concise, user-visible sequence: understand the request, validate permissions and capability gates, check the relevant file/source/repository conditions, obtain confirmation when required, execute the approved action, audit the outcome, and report the result. This gives users useful progress without disclosing private model reasoning or secrets. Ask `Lily, show operating skills` to view the available protocols, or `Lily, show tool status` to see which host-gated features are currently enabled.

Lily now applies a deterministic safety layer after both AI and heuristic planning. A provider cannot lower a destructive action’s risk or suppress its confirmation requirement. Member-targeting actions require an explicit numeric ID or direct reply. This hardening removes dead action routes for unconfigured reminders and fake task extraction; a normal summary request is handled as an AI response only, without claiming a separate automation job was created.

The current concrete admin and assistant actions include **member profile lookup**, **group-title changes**, **group-description changes**, **quoted-message explanation**, and **scoped deletion of the requester’s latest saved memory**. Group metadata changes and memory deletion retain confirmations and audits. The member lookup is read-only but remains administrator-only to avoid turning Lily into a member-enumeration tool.

## MangaDex metadata and release feed

Lily includes an **official MangaDex metadata-only** client. It is disabled by default. To enable it, set a truthful user agent and a conservative request interval; Lily caches repeated requests and never calls reader, image, MangaDex@Home, or chapter-download endpoints.

```env
LILY_ENABLE_MANGADEX_METADATA=true
LILY_MANGADEX_USER_AGENT="Lily/1.0 (your-contact@example.com)"
LILY_MANGADEX_MIN_INTERVAL_SECONDS=0.30
LILY_MANGADEX_CACHE_SECONDS=300
```

Use `Lily, MangaDex search for Frieren` to search title metadata, or `Lily, show MangaDex recent chapters for <MangaDex title ID>` to view a release feed. Lily attributes results to MangaDex and displays group attribution metadata when available; it does not provide a chapter reader or content-download feature. MangaPill remains manual-link-only because Lily has no verified authorized public API integration for it.

## Telegram Bot API 10.3 delivery and local CLI

Lily uses native Rich Messages whenever the deployed Bot API supports them and falls back gracefully for older deployments. It supports compact tables, expandable quotations, styled confirmation buttons, and optional live rich-message draft previews. The preview contains only public stages such as **validating**, **waiting for confirmation**, or **delivering**; it never exposes hidden model reasoning, system prompts, credentials, or unverified decisions. Telegram’s standard `sendMessage` text is limited to 4,096 characters after entities parsing, so Lily safely splits long answers into numbered pages below that limit rather than assuming an 8,000-character single-message allowance.[1]

The `commands/` directory contains safe host-operator scripts:

```bash
./commands/check.sh                 # compile and run all tests
./commands/cli.sh doctor            # redacted local health/config status
./commands/cli.sh run-profiles      # fixed approved managed-bot profiles
./commands/cli.sh preview "Lily set group title to Anime Club"  # preview only; does not execute
./commands/run-bot.sh               # start Telegram worker locally
./commands/run-api.sh               # start standalone FastAPI service locally
```

These scripts are intentionally for the server operator only; they do not create a generic shell tool in Telegram. The detailed current API capability protocol lives at `lily/knowledge/telegram-api/SKILL.md`.

## References

[1]: https://core.telegram.org/bots/api "Telegram Bot API reference"

## References

- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Telegram Bot Features](https://core.telegram.org/bots/features)
- [Telegram Bot API changelog](https://core.telegram.org/bots/api-changelog)
- [python-telegram-bot documentation](https://docs.python-telegram-bot.org/)
- [python-telegram-bot Rich Messages tracking issue](https://github.com/python-telegram-bot/python-telegram-bot/issues/5261)
