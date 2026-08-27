# Lily Local Commands

These scripts are for the operator on the persistent host. They do **not** expose a generic shell interface to Telegram users. Use a dedicated Linux service account, a host-only `.env` with `0600` permissions, and systemd or Docker Compose for production supervision.

| Script | Purpose |
|---|---|
| `run-bot.sh` | Starts Lily’s Telegram worker. Set `LILY_STREAM_EMBEDDED=false` when the API is a separate service. |
| `run-api.sh` | Starts the standalone FastAPI streaming/API service using host configuration. |
| `check.sh` | Runs compile and regression validation. |
| `cli.sh` | Runs the safe local Lily CLI, for example `./commands/cli.sh doctor`. |

Scripts load only an operator-provisioned `.env` file if it exists. They do not echo its content.
