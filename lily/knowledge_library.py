"""Read-only access to Lily’s curated operating knowledge.

Only bundled skill documents under ``lily/knowledge`` are exposed. This is
documentation for validated Python actions, not a mechanism for an LLM to add
tools, execute commands, or read arbitrary files.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).with_name("knowledge")
SKILLS = {
    "agent-workflow": "Safe plan validation, confirmation, execution, and audit stages.",
    "moderation": "Group moderation controls, permissions, verification, and audits.",
    "media": "File handling, rename, queues, encoding, streaming, and source safeguards.",
    "channels": "Rich channel drafts, publish verification, and post management.",
    "model-routing": "Private provider fallback order, health, cooldowns, and privacy tiers.",
    "bot-operations": "Approved bot projects, environment templates, and dry-run provisioning.",
    "deployment": "Persistent-host configuration, recovery, health, and service operations.",
    "miniapp": "Telegram Mini App authentication and authorization boundaries.",
}


def catalog() -> list[dict[str, str]]:
    return [{"name": name, "summary": summary} for name, summary in SKILLS.items()]


def read_skill(name: str, limit: int = 1_800) -> str:
    """Return a bounded bundled protocol; unknown names never become paths."""
    if name not in SKILLS:
        raise KeyError("Unknown Lily operating skill.")
    path = ROOT / name / "SKILL.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else SKILLS[name]
    return text[:max(200, min(limit, 4_000))]


def planning_policy() -> str:
    return read_skill("agent-workflow", limit=1_400)
