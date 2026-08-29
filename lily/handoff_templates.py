"""NEXUS-style handoff cards for Lily's bounded specialist team."""

from __future__ import annotations

from typing import Any

from .agent import Plan
from .agent_roles import CATALOG, assign_roles


def build_handoff(plan: Plan, from_role: str | None = None, to_role: str | None = None) -> dict[str, Any]:
    """Return a compact, user-visible handoff packet — no private memo text."""
    assignment = assign_roles(plan)
    primary = assignment.primary
    reviewers = assignment.reviewers
    source = from_role or "Lily Orchestrator"
    target = to_role or primary.name
    acceptance = _acceptance_criteria(plan)
    return {
        "from": source[:80],
        "to": target[:80],
        "action": plan.action,
        "risk": plan.risk,
        "summary": plan.summary[:500],
        "deliverable": primary.deliverable[:200],
        "acceptance_criteria": acceptance,
        "missing": [str(item)[:180] for item in plan.missing[:6]],
        "reviewers": [role.name for role in reviewers[:3]],
        "requires_confirmation": plan.requires_confirmation,
    }


def handoff_blocks(packet: dict[str, Any]) -> list[str]:
    lines = [
        f"**Handoff:** {packet['from']} → {packet['to']}",
        f"**Action:** `{packet['action']}` · **Risk:** {packet['risk']}",
        f"**Summary:** {packet['summary']}",
        f"**Deliverable:** {packet['deliverable']}",
    ]
    if packet.get("acceptance_criteria"):
        lines.append("**Acceptance:**")
        lines.extend(f"• {item}" for item in packet["acceptance_criteria"][:5])
    if packet.get("missing"):
        lines.append("**Still needed:**")
        lines.extend(f"• {item}" for item in packet["missing"])
    if packet.get("reviewers"):
        lines.append(f"**Reviewers:** {', '.join(packet['reviewers'])}")
    if packet.get("requires_confirmation"):
        lines.append("**Gate:** explicit confirmation required before execution.")
    return lines


def _acceptance_criteria(plan: Plan) -> list[str]:
    action = plan.action
    common = ["Permissions validated", "Targets scoped to this chat", "Audit event recorded"]
    specific: dict[str, list[str]] = {
        "create_code_project": ["Isolated workspace created", "ZIP archive delivered", "No arbitrary code execution"],
        "web_search": ["Configured provider used", "Results deduplicated and bounded"],
        "ban_user": ["Administrator authority confirmed", "Target user identified"],
        "publish_channel_post": ["Channel admin rights verified", "Draft reviewed before publish"],
        "generate_image": ["Prompt confirmed", "Provider configured and authorized"],
        "export_audit": ["Admin-only export", "No secrets in CSV"],
    }
    return (specific.get(action, ["Named Lily tool executed only"]) + common)[:6]


def role_handoff_chain(plan: Plan) -> list[dict[str, Any]]:
    """Build a short chain of handoffs for multi-role workflows."""
    assignment = assign_roles(plan)
    chain: list[dict[str, Any]] = []
    previous = "Lily Orchestrator"
    for role in (assignment.primary, *assignment.reviewers):
        chain.append(build_handoff(plan, from_role=previous, to_role=role.name))
        previous = role.name
    return chain
