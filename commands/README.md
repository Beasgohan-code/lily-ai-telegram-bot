# Lily Local Commands

These scripts are for the operator on the persistent host. They do **not** expose a generic shell interface to Telegram users. Use a dedicated Linux service account, a host-only `.env` with `0600` permissions, and systemd or Docker Compose for production supervision.

| Script | Purpose |
|---|---|
| `run-bot.sh` | Starts Lily’s Telegram worker. Set `LILY_STREAM_EMBEDDED=false` when the API is a separate service. |
| `run-api.sh` | Starts the standalone FastAPI streaming/API service using host configuration. |
| `check.sh` | Runs compile and regression validation. |
| `cli.sh` | Runs the safe local Lily CLI, for example `./commands/cli.sh doctor`. |
| `ubuntu-sandbox.sh` | One safe Ubuntu terminal entrypoint for Lily diagnostics, agent planning, validation, and foreground services. |

Scripts load only an operator-provisioned `.env` file if it exists. They do not echo its content.

## Ubuntu terminal agent

For a compact terminal interface, run `./commands/ubuntu-sandbox.sh help`. The `sandbox` option shows fixed, redacted local runtime capabilities. The `search "..."` option uses Lily’s configured web-search provider and prints structured results. The `agent` command plans ordinary-language requests and prints only the action, risk, confirmation requirement, missing details, and visible stages. It **never executes** a plan, so it cannot become a generic terminal shell. Use `agent --ask "..."` for a local conversational answer.

## Code creator workspace

Lily’s code creator writes only under `work/code-workspaces/<owner>/<project>/`. It supports starter files for Python, JavaScript, TypeScript, HTML, CSS, JSON, YAML, Bash, Java, C#, Go, and Rust. Use `workspace create demo python "simple CLI demo"`, `workspace mkdir demo src`, `workspace write demo src/helpers.py "def hello(): return 'hi'"`, `workspace tree demo`, `workspace zip demo`, and `workspace validate demo`.

`validate` performs only fixed syntax checks for Python and JSON; it does **not** execute generated code. In Telegram, ordinary-language code-creator requests produce a Lily-owned starter workspace and deliver a ZIP archive after safe public progress stages. No arbitrary shell command is accepted through Telegram or this console.

The `bot` and `api` commands intentionally run in the foreground for local development. The available terminal actions are fixed (`doctor`, `sandbox`, `status`, `search`, `agent`, `check`, `bot`, and `api`) and do not accept arbitrary commands. A sandbox terminal is not a permanent host; use a supervised service on an always-on Ubuntu machine for production.

## Managed service supervisor

`./commands/ubuntu-sandbox.sh service status <slug> --owner <telegram-user-id>` can inspect only an explicitly registered and allow-listed managed service. `start`, `stop`, `restart`, and `logs` use fixed `systemctl --user` or `journalctl --user` argument lists; none accepts a shell command. The supervisor is **disabled by default**. Before enabling it on an always-on Ubuntu host, set `LILY_ENABLE_MANAGED_SERVICE_SUPERVISOR=true`, list exact registered slugs in `LILY_ALLOWED_MANAGED_SERVICES`, and install their corresponding `lily-managed-<slug>.service` units. Service logs are redacted before display.

## LLM orchestration and automatic skills

Use `./commands/ubuntu-sandbox.sh skill-match <chat_id> <user_id> "<message>"` to obtain a non-executing preview. It reports whether Lily would select a matching automatic skill or fall back to the LLM agent plan, along with a safe action summary, risk, confirmation requirement, cooldown state, and public stages. Use `./commands/ubuntu-sandbox.sh skill-runs <chat_id> --user-id <user_id>` to inspect redacted run outcomes. These operator commands cannot execute a skill or interpret text as a shell command.

## Specialist agent roles

`./commands/ubuntu-sandbox.sh roles` lists Lily’s independently designed **200-plus** specialist role cards across engineering, design, product, quality, security, operations, research, analysis, communication, community, content, media, automation, strategy, finance, academic, geospatial, healthcare, and game development. Use `./commands/ubuntu-sandbox.sh roles --division engineering` to inspect one division. A request is assigned a primary role and, where needed, reviewers such as Safety Reviewer, Privacy Guardian, and Test Engineer. Roles organize a single accountable Lily workflow; they do not create arbitrary subprocesses, external accounts, privileged tools, or hidden reasoning.
