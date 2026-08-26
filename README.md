# Lily — AI-first Telegram backend

Lily is a Python backend for an AI-first Telegram assistant and group manager. It uses `python-telegram-bot` for updates and standard Telegram actions, while calling the new RichMessage methods through a small raw HTTP client because the current typed PTB release may not expose every newest rich-message type yet.

## What is implemented

Lily accepts ordinary language instead of requiring a command-driven workflow. A private message or a group mention such as `Lily, ban this user` is converted into a strict action plan. Group moderation, file transformations, and other risky operations are routed through permission checks and confirmation cards with Yes, No, and Details buttons.

The backend includes per-user and per-chat daily and monthly request quotas, daily and monthly byte quotas, SQLite persistence, pending-action expiration, audit logs, custom trigger skills, RichMessage headings/tables/quotations/details, private rich draft progress when supported, document creation in TXT/Markdown/JSON/CSV/HTML/PDF, safe file renaming, ZIP compression, FFmpeg encoding, a rights-respecting direct-audio downloader, fallback AI-key rotation, and a channel-post studio.

The audio downloader intentionally does **not** scrape or rip streaming platforms. It accepts direct audio URLs only when the administrator explicitly enables downloads and configures an allow-list. Use it only for material you own, have permission to download, or that is legally available for download.

## Current limitations and extension points

Mira-style external integrations, proactive reminders, image generation, deep web research, and advanced memory retrieval are represented as safe router actions and extension points, but they require provider-specific connectors. The core intentionally refuses to claim that such an action completed until an integration is implemented. Lily’s built-in post search indexes posts that Lily publishes itself; searching arbitrary historical channel messages requires an additional authorized Telegram user-session connector and is intentionally not enabled by default.

The supplied Auto-Rename, AniwatchTvdl, ENCODING-BOT, FileToLink, LLM retrieval, and Post-Search-Bot repositories informed Lily’s filename/caption patterns, AniList fallback lookup, FFmpeg settings, progress queues, document retrieval concepts, and indexed search. Their code was not blindly merged: the provided repositories include different copyleft or missing-license conditions, so Lily contains independently implemented compatible logic. In particular, host-bypass download utilities and arbitrary shell-execution patterns were excluded.

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

For fallback support, set `LILY_AI_KEYS` to a comma-separated list of keys. Set `LILY_AI_BASES` to the matching comma-separated list of API bases, or provide one base that will be reused for all keys. Lily moves to the next provider after authentication, rate-limit, timeout, conflict, or server errors.

For advanced multi-model routing, set `LILY_AI_PROFILES_JSON`. Each profile may define `name`, `api_key`, `base_url`, `model`, `family`, `capabilities`, `priority`, and `max_retries`. Lily selects only profiles supporting the requested capability, converts reasoning and token parameters for GPT, Claude, and Gemini families, records success/failure latency, and temporarily cools down unhealthy profiles. `model_status` can report current health in chat.

## Custom skill plugins

Trusted local plugins live in the `plugins/` directory. Each plugin defines a `PLUGIN` manifest with a name, version, description, trigger list, an allow-listed Lily action, risk level, and optional `build_plan(context)` function. A plugin receives text and IDs, not a Telegram Bot object, so all Telegram operations still pass through Lily’s permission and confirmation layer. The included `plugins/hello_skill.py` is a safe example. Do not load untrusted plugin files; Python plugins can execute arbitrary code by design.

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
Lily, create a skill: when someone says “drop the link”, ask an admin before deleting the message.
```

The user should reply directly to a target message or file when Lily needs an unambiguous target. This prevents the AI from guessing which member or file the user meant.

## Security checklist

Use a separate bot token for development, set restrictive filesystem permissions on `data`, `work`, and `downloads`, configure disk quotas, keep the Bot API server private, run the process as a non-root user, and review audit logs. Do not enable direct audio downloads without an allow-list. Do not let custom skills contain arbitrary shell commands; skills are restricted to named backend actions.

## References

- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Telegram Bot Features](https://core.telegram.org/bots/features)
- [Telegram Bot API changelog](https://core.telegram.org/bots/api-changelog)
- [python-telegram-bot documentation](https://docs.python-telegram-bot.org/)
- [python-telegram-bot Rich Messages tracking issue](https://github.com/python-telegram-bot/python-telegram-bot/issues/5261)
