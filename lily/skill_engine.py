"""Safe automatic selection for database-backed Lily skills.

Automatic matching is deliberately separate from execution: only approved safe
actions may run unattended. All other matched skills become a user-visible plan
that keeps Lily's normal confirmation and admin checks intact.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from .agent import ACTIONS, Plan


# Sending a fixed, database-stored reply is the only custom-skill action that
# can run without a requester confirmation. File, moderation, network, and
# state-changing actions are always converted into an approval-gated plan.
AUTO_SAFE_ACTIONS = frozenset({"plugin_reply"})
VALID_MODES = frozenset({"auto", "suggest"})


@dataclass(frozen=True)
class SkillMatch:
    skill_id: str
    name: str
    action: str
    state: str
    plan: Plan | None
    cooldown_remaining: int = 0

    def public_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id[:12],
            "name": self.name,
            "action": self.action,
            "state": self.state,
            "cooldown_remaining_seconds": self.cooldown_remaining,
            "requires_confirmation": bool(self.plan and self.plan.requires_confirmation),
            "risk": self.plan.risk if self.plan else "safe",
            "public_stages": self.plan.public_stages() if self.plan else [],
            "executes": False,
        }


def _match_trigger(trigger: dict[str, Any], text: str) -> bool:
    mode = str(trigger.get("match", trigger.get("mode", "contains"))).lower()
    if mode == "regex":
        patterns = trigger.get("patterns", trigger.get("regex", trigger.get("keywords", [])))
        for pattern in patterns if isinstance(patterns, list) else [patterns]:
            try:
                if re.search(str(pattern), text, re.IGNORECASE):
                    return True
            except re.error:
                continue
        return False
    keywords = trigger.get("keywords", [])
    contains = trigger.get("contains", [])
    if not isinstance(keywords, list):
        keywords = [keywords]
    if not isinstance(contains, list):
        contains = [contains]
    normalized = text.lower()
    for keyword in keywords:
        value = str(keyword).strip()
        if value and re.search(rf"(?<!\w){re.escape(value)}(?!\w)", text, re.IGNORECASE):
            return True
    return any(str(value).strip().lower() in normalized for value in contains if str(value).strip())


def _skill_action(skill: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    action_value = skill.get("action") if isinstance(skill.get("action"), dict) else {}
    action = str(action_value.get("action") or action_value.get("type") or "none")
    args = action_value.get("args") if isinstance(action_value.get("args"), dict) else action_value
    args = dict(args) if isinstance(args, dict) else {}
    return (action if action in ACTIONS else "none"), args


def select_skill(skills: list[dict[str, Any]], text: str, now: int | None = None) -> SkillMatch | None:
    """Return the highest-priority matching skill without recording or executing it."""
    now = int(time.time()) if now is None else int(now)
    candidates = sorted(
        (item for item in skills if int(item.get("enabled", 1))),
        key=lambda item: (-int(item.get("priority", 100)), int(item.get("created_at", 0))),
    )
    for skill in candidates:
        trigger = skill.get("trigger") if isinstance(skill.get("trigger"), dict) else {}
        if not _match_trigger(trigger, text):
            continue
        action, args = _skill_action(skill)
        if action == "none":
            continue
        cooldown = max(0, min(int(skill.get("cooldown_seconds", 0) or 0), 86_400))
        last_run = int(skill.get("last_run_at", 0) or 0)
        remaining = max(0, last_run + cooldown - now)
        if remaining:
            return SkillMatch(str(skill["id"]), str(skill["name"])[:80], action, "cooldown", None, remaining)
        mode = str(skill.get("execution_mode", "suggest")).lower()
        confirmation = str(skill.get("confirmation", "risky")).lower()
        automatic = mode == "auto" and confirmation == "never" and action in AUTO_SAFE_ACTIONS
        plan = Plan.from_dict({
            "intent": str(skill.get("name") or "automatic skill"),
            "summary": f"Run skill: {str(skill.get('name') or 'Custom Lily skill')[:80]}",
            "action": action,
            "risk": "safe" if automatic else "risky",
            "requires_confirmation": not automatic,
            "args": args,
            "missing": [],
            "confidence": 1.0,
        })
        if not automatic:
            plan.risk = "risky" if plan.risk == "safe" else plan.risk
            plan.requires_confirmation = True
        plan.enforce_safety()
        return SkillMatch(str(skill["id"]), str(skill["name"])[:80], action, "automatic" if automatic else "approval_required", plan)
    return None
