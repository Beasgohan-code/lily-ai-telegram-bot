# Managed Bot Operations Skill

Lily can register approved bot projects with an exact HTTPS GitHub repository allow-list, a validated slug, a fixed isolated project path, a branch, an owner, a supported runtime, and a fixed run profile. The only run profiles are Python entrypoint, Python module, Node start script, and Docker Compose. Lily must not accept free-form shell commands from chat.

Provisioning begins in dry-run mode. Real provisioning requires both host gates, a project-specific confirmation, an approved repository, and a supported dependency manifest. Python projects use an isolated `.venv`; requirements installs record a digest so changed dependencies require renewed review. Environment templates are parsed from `.env.example`, redacted in chat, validated, atomically written with mode 0600, and never committed to Git.

Lifecycle actions and logs require a persistent-host supervisor. They must use fixed systemd units and bounded, redacted journal retrieval rather than in-memory PIDs or raw filesystem browsing.
