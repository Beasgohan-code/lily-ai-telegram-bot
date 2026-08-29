"""Bounded specialist-team support for Lily's centrally controlled planner.

This module selects a small review team from the catalog and only merges safety
escalations or missing details into the primary Plan. It never exposes or grants
tools, and it never turns role output into executable arguments or new actions.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from .agent import Plan, RISK_LEVEL
from .agent_roles import CATALOG, assign_roles


_SENSITIVE = re.compile(
    r"(?i)(\b(?:api[_ -]?key|token|secret|password|authorization|bearer)\b\s*(?:[:=]|is)\s*)([^\s,;]{4,})"
)
_RAW_COMMAND = re.compile(r"(?im)^\s*(?:[$#>]\s*|(?:sudo|curl|wget|rm|python(?:3)?|bash|systemctl)\b).*$")
_PRIVATE_REASONING = re.compile(r"(?is)\b(?:chain[ -]?of[ -]?thought|private reasoning|internal analysis)\b.*")


def redact_team_text(value: object, limit: int = 3500) -> str:
    """Keep specialist prompts concise and remove common credential values."""
    text = str(value or "").replace("\x00", " ")
    text = _SENSITIVE.sub(r"\1[redacted]", text)
    text = _RAW_COMMAND.sub("[private command detail removed]", text)
    text = _PRIVATE_REASONING.sub("[private reasoning removed]", text)
    return text[:limit]


def select_roles(plan: Plan, text: str, limit: int) -> list[Any]:
    """Return the primary specialist and at most two context-relevant reviewers."""
    limit = max(1, min(int(limit), 4))
    assigned = assign_roles(plan)
    selected = [assigned.primary, *assigned.reviewers]
    low = text.lower()
    additions: list[str] = []
    if any(term in low for term in ("code", "python", "javascript", "api", "database", "bug", "project")):
        additions.extend(["backend-architect", "code-reviewer", "test-engineer"])
    if any(term in low for term in ("design", "mini app", "website", "ui", "ux")):
        additions.extend(["frontend-builder", "ux-reviewer", "accessibility-reviewer"])
    if any(term in low for term in ("security", "token", "privacy", "secret", "permission")):
        additions.extend(["privacy-guardian", "security-01"])
    if any(term in low for term in ("deploy", "server", "service", "host", "incident", "log")):
        additions.extend(["service-operator", "incident-responder", "operations-02"])
    if plan.action == "none":
        additions.append("product-manager")
    for slug in additions:
        role = CATALOG.get(slug)
        if role and role not in selected:
            selected.append(role)
        if len(selected) >= limit:
            break
    return selected[:limit]


def role_review_context(text: str, plan: Plan) -> dict[str, Any]:
    """Return the only request context that a reviewer receives."""
    return {
        "request": redact_team_text(text),
        "central_plan": {
            "summary": redact_team_text(plan.summary, 500),
            "action": plan.action,
            "risk": plan.risk,
            "requires_confirmation": plan.requires_confirmation,
            "missing": [redact_team_text(item, 180) for item in plan.missing[:8]],
        },
    }


def merge_role_reviews(plan: Plan, memos: Iterable[Any]) -> Plan:
    """Safety-merge role reviews without accepting new actions or arguments."""
    materialized = list(memos)
    highest = max([plan.risk, *(str(memo.risk) for memo in materialized)], key=lambda value: RISK_LEVEL.get(value, 0))
    missing = list(dict.fromkeys([
        *plan.missing,
        *(redact_team_text(item, 180) for memo in materialized for item in memo.missing),
    ]))[:8]
    result = Plan.from_dict({
        "intent": plan.intent,
        "summary": redact_team_text(plan.summary, 1000),
        "action": plan.action,
        "risk": highest,
        "requires_confirmation": plan.requires_confirmation or any(bool(memo.requires_confirmation) for memo in materialized),
        "args": dict(plan.args),
        "missing": missing,
        "confidence": plan.confidence,
    }).enforce_safety()
    result.args["_agent_team"] = {
        "mode": "llm-reviewed",
        "members": [
            {
                **memo.public_dict(),
                "summary": redact_team_text(memo.summary, 280),
                "missing": [redact_team_text(item, 180) for item in memo.missing],
            }
            for memo in materialized
        ],
        "reviewed_count": len(materialized),
    }
    return result


def public_team_summary(plan: Plan) -> dict[str, Any]:
    """Return terse status only; private memo text is never part of public progress."""
    value = plan.args.get("_agent_team") if isinstance(plan.args, dict) else None
    if not isinstance(value, dict):
        return {"mode": "catalog-assignment", "reviewed_count": 0, "roles": []}
    members = value.get("members") if isinstance(value.get("members"), list) else []
    roles = []
    for member in members[:4]:
        if not isinstance(member, dict):
            continue
        role = redact_team_text(member.get("role"), 100)
        division = redact_team_text(member.get("division"), 60)
        if role:
            roles.append({"role": role, "division": division})
    try:
        reviewed_count = max(0, int(value.get("reviewed_count", 0) or 0))
    except (TypeError, ValueError):
        reviewed_count = 0
    return {
        "mode": "llm-reviewed" if value.get("mode") == "llm-reviewed" else "catalog-assignment",
        "reviewed_count": min(len(roles), reviewed_count),
        "roles": roles,
    }


def public_team_stages(plan: Plan) -> list[str]:
    summary = public_team_summary(plan)
    if not summary["reviewed_count"]:
        return []
    labels = ", ".join(item["role"] for item in summary["roles"][:3])
    return [f"Bounded specialist review complete: {labels}"]
