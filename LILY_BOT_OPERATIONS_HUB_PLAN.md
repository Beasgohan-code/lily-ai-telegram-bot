# Lily Bot-Operations Hub Plan

## What Lily can become

Lily can act as a controlled operations assistant for multiple Telegram bot projects. An administrator could say:

```text
Lily, create a project called manga-bot from this GitHub repository: https://github.com/example/manga-bot
Lily, show me the environment variables required by manga-bot.
Lily, start manga-bot.
Lily, stop manga-bot.
Lily, restart manga-bot and show the last 100 lines of logs.
Lily, update manga-bot from its approved branch, but show me the changes first.
```

The important boundary is that Lily must not become an unrestricted remote shell. Every managed bot should have a registered project manifest, an approved repository, a fixed project directory, an explicit start command, an explicit environment schema, a resource policy, and an owner. Lifecycle actions should be executed through a supervisor such as systemd, not by constructing arbitrary shell commands from chat text.

## Hosting reality

The current development sandbox is not suitable for hosting Lily or other bots continuously because it can hibernate. A real deployment needs an always-on machine. The lightest option is a managed persistent web process for the API when the workload stays within its runtime limits. Lily’s Local Bot API server, FFmpeg jobs, Docker, multiple bot processes, and large media files require OS-level control and more storage, so an Ubuntu server or an existing VPS is the practical production route.

| Hosting route | Best fit | Trade-offs | Approximate cost |
|---|---|---|---:|
| Managed always-on web service | Lily API and a light bot worker with modest resource needs | No root, no Docker, limited control over FFmpeg and local Bot API; unsuitable for several heavy bots | Usage-based; reserved capacity is quoted separately by the platform |
| Ubuntu cloud server | Lily, Local Bot API, FFmpeg, multiple bot projects, systemd, private directories, and log control | Requires firewall, upgrades, backups, monitoring, and secret management | Basic $10/month, Standard $30/month, Advanced $50/month; outbound overage can apply |
| Existing VPS or home server | Users who already have a reachable Linux host | User manages uptime, IP/DNS, backups, and security | Depends on the provider or existing hardware |

For the Ubuntu route, the Basic tier is appropriate only for Lily plus one lightweight bot and small media workloads. A Standard-sized machine is a safer starting point for Lily, the Local Bot API, FFmpeg, SQLite backups, and a manga bot running concurrently. No GPU should be assumed. The server must keep outbound-traffic usage under its allowance or be configured to avoid unexpected shutdown when the allowance is exhausted.

## Target topology

```text
Telegram users
      |
      v
Lily operator bot ---------------> Telegram Bot API / Local Bot API
      |
      +--> Bot registry database
      +--> Approved project manifests
      +--> systemd service units
      +--> /srv/lily/projects/<slug>
      +--> /srv/lily/env/<slug>.env  (0600, never committed)
      +--> journalctl logs with redaction
      +--> FFmpeg and media work queues
      |
      +--> FastAPI API / signed streaming gateway behind HTTPS
      |
      +--> Mini App after Telegram initData verification
```

The operator bot and managed bots should run as separate Unix services and, preferably, separate Unix users. Lily should not run other bots as root. Each project should have its own working directory, virtual environment or container, environment file, service unit, resource limits, and log namespace.

## Managed project record

Each registered project should contain the following fields in Lily’s database:

| Field | Purpose |
|---|---|
| `slug` | Stable safe identifier such as `manga-bot`; never derived directly into a shell command without validation. |
| `repository_url` | Approved HTTPS GitHub repository URL. SSH URLs and arbitrary hosts should be disabled unless explicitly configured. |
| `branch` | Approved branch, normally `main` or a pinned release branch. |
| `project_root` | Fixed path under the projects root; path traversal is rejected. |
| `runtime` | Python, Node, Docker Compose, or another explicitly supported runtime. |
| `install_command` | Selected from an allow-list, not supplied as free-form chat text. |
| `start_command` | Fixed command or generated systemd `ExecStart`; never arbitrary shell input. |
| `env_schema` | Required, optional, secret, boolean, integer, URL, and redaction metadata for each variable. |
| `service_name` | Exact systemd service name generated from the validated slug. |
| `owner_id` | Telegram administrator who created or adopted the project. |
| `status` | Registered, provisioning, stopped, running, failed, updating, or archived. |
| `revision` | Last approved commit SHA and deployment timestamp. |

## Safe provisioning workflow

Lily should use a two-stage flow. First it produces a dry-run preview containing the repository, branch, target directory, detected runtime, required variables, install plan, start command, and estimated resource policy. The administrator confirms. Only then does a host-side worker clone the repository into the fixed projects root, create the runtime environment, install dependencies from a locked or reviewed manifest, write the environment file with mode `0600`, create the service unit, and perform a health check.

The environment file should never be generated from values pasted into a public group. Lily should ask for each secret through a private admin conversation or an authenticated Mini App form, redact secrets from progress messages, and refuse to echo them back. The repository’s `.env.example` may be displayed, but the final `.env` belongs only on the host.

## Lifecycle controls

The initial natural-language lifecycle surface should be deliberately small and explicit:

| Request | Action | Confirmation |
|---|---|---|
| `show all managed bots` | Read-only registry and service status | No |
| `show manga-bot status` | Read service state and recent health result | No |
| `start manga-bot` | Start the exact approved systemd unit | Yes on first use or after a failed deployment |
| `stop manga-bot` | Stop the exact approved unit | Yes |
| `restart manga-bot` | Restart the exact approved unit | Yes |
| `show manga-bot logs` | Return redacted, paginated recent logs | No |
| `update manga-bot` | Fetch approved branch and show revision diff | Yes, twice if migrations are detected |
| `rollback manga-bot` | Restore the last approved revision or snapshot | Yes |
| `archive manga-bot` | Disable its unit and remove it from active controls | Yes; never delete files automatically |

Lily should reject commands such as `run this shell command`, `execute arbitrary Python`, `sudo`, `rm -rf`, or a repository URL that is not on the administrator’s allow-list. The bot-factory feature should not provide a generic terminal through Telegram.

## Log delivery

The log tool should read only the selected service’s journal namespace, apply a maximum line and byte limit, redact tokens, cookies, authorization headers, private keys, and values matching configured secret names, and paginate older entries. A normal response should show severity, timestamp, service name, and a short message. Full raw logs should never be posted automatically into a public group.

A useful natural-language interface is:

```text
Lily, show manga-bot errors from the last 30 minutes.
Lily, show the last 100 lines for manga-bot.
Lily, is manga-bot healthy?
```

Every start, stop, restart, update, rollback, failed health check, and log export should create an audit event containing the actor, project, operation, result, and revision. Secrets and raw log bodies must not be stored in that audit record.

## Environment contract

The operator service should use a host-level environment file such as `/etc/lily/lily.env`, owned by root and readable by the Lily service account through a dedicated group. A safe initial template is:

```env
# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_LOCAL_MODE=true
TELEGRAM_API_BASE=http://127.0.0.1:8081/bot
TELEGRAM_FILE_BASE=http://127.0.0.1:8081/file/bot
LILY_ADMIN_USER_IDS=

# Lily data and host integration
LILY_DATABASE=/srv/lily/data/lily.sqlite3
LILY_WORK_DIR=/srv/lily/work
LILY_DOWNLOAD_DIR=/srv/lily/downloads
LILY_PROJECTS_ROOT=/srv/lily/projects
LILY_ENV_ROOT=/srv/lily/env
LILY_SUPERVISOR_MODE=systemd
LILY_ALLOWED_REPOSITORIES=
LILY_ALLOWED_PROJECTS=
LILY_DRY_RUN=true
LILY_LOG_LEVEL=INFO
LILY_LOG_MAX_LINES=200
LILY_LOG_MAX_BYTES=200000
LILY_LOG_REDACTION=true

# Provider order and privacy
LILY_AI_PRESETS=all
LILY_FALLBACK_ORDER=free,gemini,openai,groq
LILY_ALLOW_PUBLIC_AI_FALLBACKS=false
OPENAI_API_KEY=
GEMINI_API_KEY=
GROQ_API_KEY=

# Streaming and public API
LILY_STREAM_PUBLIC_BASE_URL=
LILY_STREAM_SIGNING_SECRET=
LILY_STREAM_BIND_HOST=127.0.0.1
LILY_STREAM_PORT=8090
LILY_STREAM_EMBEDDED=false

# Limits
LILY_MAX_FILE_BYTES=1900000000
LILY_MAX_JOB_BYTES=2000000000
LILY_MAX_CONCURRENT_JOBS=2
LILY_DAILY_REQUEST_LIMIT=100
LILY_MONTHLY_REQUEST_LIMIT=3000
```

Provider keys should be entered through the host’s secret mechanism rather than committed to GitHub. Each managed bot gets a separate `/srv/lily/env/<slug>.env` with only the variables it needs. Lily should support a redacted environment-status view that reports `configured`, `missing`, or `invalid-format`, never the value.

## Advanced features worth adding next

| Priority | Feature | Result |
|---:|---|---|
| 1 | Bot factory registry | Create, adopt, rename, archive, and inspect approved bot projects from natural language. |
| 2 | Environment wizard | Read `.env.example`, classify variables, request missing secrets privately, and validate formats. |
| 3 | Supervisor controller | Start, stop, restart, status, and auto-restart approved services through fixed systemd units. |
| 4 | Safe Git deployment | Preview commits and diffs, pin a SHA, update only after confirmation, and provide rollback. |
| 5 | Redacted log center | Query service logs by time, severity, and project with pagination and audit trails. |
| 6 | Health and resource monitor | Report CPU, memory, disk, process age, queue depth, and repeated restart loops. |
| 7 | Backup manager | Snapshot project manifests, environment schemas, database metadata, and configuration while excluding secrets and raw media. |
| 8 | Multi-bot policy engine | Apply per-bot quotas, allowed commands, maintainer roles, time windows, and maintenance mode. |
| 9 | Mini App operations console | Replace static dashboard data with verified Telegram sessions and live project controls. |
| 10 | Approval workflow | Require two-person approval for public deployments, destructive actions, migrations, or secret rotation. |

## Recommended implementation order

First deploy Lily itself with the current stable bot and FastAPI configuration. Next add a read-only registry and health/log viewer. Then add dry-run provisioning for one test repository. After that, enable start and stop controls for a single test bot, followed by update and rollback. Only when those flows are audited and tested should Lily manage a manga bot or multiple unrelated services.

The first production test should use a disposable bot token, a private test repository, a non-production group, and a test domain. The deployment should confirm that a stopped bot stays stopped across a Lily restart, a failed bot is reported accurately, secrets are absent from Git history and logs, and a rollback restores the previously approved revision.

## Current limitation and required host decision

I can prepare the code, service files, environment templates, and GitHub repository here, but I cannot keep the current ephemeral sandbox running as a 24/7 host. To actually host Lily and operate other bot projects, choose an always-on Ubuntu server, an existing VPS, or a managed runtime that supports the required Python, FFmpeg, Docker, and system-service boundaries. If using a managed Ubuntu server, it must use restrictive UFW rules, automatic service startup after reboot, daily backups, and monitoring for disk and outbound-traffic limits.

*Prepared by Manus AI.*

## References

[1]: https://core.telegram.org/bots/api "Telegram Bot API"
[2]: https://core.telegram.org/bots/webapps "Telegram Mini Apps"
[3]: https://systemd.io/ "systemd Documentation"
[4]: https://docs.docker.com/compose/ "Docker Compose Documentation"
