# Bot-Host Reference Assessment

The user-provided `Beasgohan-code/bot-host` repository was reviewed as reference material. Its visible GitHub page describes a unified Telegram bot hosting platform with a dashboard, Docker support, project folders, process monitoring, restart behavior, environment-file editing, and per-bot logs. The clone did not contain a `LICENSE` file, despite the page presenting an MIT label, so Lily must not copy source code from it. This assessment records independently derived concepts only.

| Reference pattern | Lily adaptation | Safety adjustment |
|---|---|---|
| One project folder per owner and project | Fixed, validated path under `LILY_PROJECTS_ROOT/<slug>` | Lily does not interpolate a user ID or arbitrary path from chat into filesystem operations. |
| Per-project Python virtual environment | Create `.venv` inside each approved Python project | Dependencies are installed only after an explicit administrator confirmation and repository allow-list check. |
| Requirements-file hash marker | Save a digest after an approved successful install | A changed digest causes a new review/confirmation requirement; it never silently reinstalls. |
| Run command parsed with shell-style tokenization | Fixed runtime profiles and validated entrypoint/module targets | No arbitrary `sh`, `bash`, `sudo`, `curl | sh`, or free-form chat command is allowed. |
| In-memory subprocess tracking | Planned systemd service units and durable registry state | State survives Lily restarts, supports service isolation, resource limits, and host-level audit trails. |
| Per-project log files | Planned bounded, redacted journal or file-log reader | Never post raw secrets or unlimited logs into a public Telegram group. |

The next implementation adopts the virtual-environment and requirements-digest concepts in Lily’s existing secure bot factory. Lifecycle actions, automatic restarts, and logs will be implemented through an approved service supervisor rather than source-derived subprocess code.

## Reference

[1]: https://github.com/Beasgohan-code/bot-host/tree/main "Beasgohan-code bot-host repository"
