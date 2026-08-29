"""Advanced multi-agent swarm for Lily — public staged collaboration.

Specialists never bypass Plan risk/confirmation. They only:
  1. Shape public progress stages (live tg-thinking UI)
  2. Suggest missing details / safety escalations
  3. Enrich summaries for the user-facing card

Execution always stays on the central execute_plan path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .agent import Plan
from .agent_roles import CATALOG, AgentRole, assign_roles
from .agent_team import public_team_summary, redact_team_text
from .rich import (
    buttons_block,
    divider,
    heading,
    live_action,
    paragraph,
    rich_message_button,
    rich_text_button,
    table,
    thinking,
)


# --- Telegram-ops specialist routing -----------------------------------------

_ACTION_SPECIALISTS: dict[str, list[str]] = {
    "ban_user": ["group-ops-lead", "community-moderator", "safety-reviewer"],
    "unban_user": ["community-moderator", "safety-reviewer"],
    "kick_user": ["community-moderator", "safety-reviewer"],
    "mute_user": ["community-moderator", "safety-reviewer"],
    "unmute_user": ["community-moderator"],
    "promote_admin": ["community-moderator", "safety-reviewer", "privacy-guardian"],
    "demote_admin": ["community-moderator", "safety-reviewer"],
    "rename_group": ["community-moderator", "channel-editor"],
    "set_group_description": ["community-moderator", "channel-editor"],
    "create_invite_link": ["community-moderator", "privacy-guardian"],
    "create_poll": ["poll-designer", "community-moderator", "product-manager"],
    "publish_channel_post": ["channel-publisher", "channel-editor", "privacy-guardian"],
    "shorten_url": ["url-guardian", "research-scout", "privacy-guardian"],
    "generate_image": ["media-engineer", "ux-reviewer"],
    "generate_video": ["media-engineer", "streaming-engineer"],
    "encode_media": ["media-engineer"],
    "create_code_project": ["code-creator", "backend-architect", "test-engineer"],
    "web_search": ["research-scout", "knowledge-curator"],
    "weather_lookup": ["research-scout"],
    "remember": ["knowledge-curator", "privacy-guardian"],
}


@dataclass
class SwarmMember:
    role: AgentRole
    status: str = "queued"  # queued | active | done | blocked
    note: str = ""

    def public_dict(self) -> dict[str, str]:
        return {
            "role": self.role.name,
            "division": self.role.division,
            "status": self.status,
            "note": redact_team_text(self.note, 160),
            "deliverable": self.role.deliverable,
        }


@dataclass
class SwarmPlan:
    """Ordered specialist squad for one user request."""
    members: list[SwarmMember] = field(default_factory=list)
    mode: str = "swarm"
    lead: str = "Lily Orchestrator"

    def stages(self) -> list[str]:
        return [f"{m.role.name}" for m in self.members[:8]]

    def active_index(self) -> int:
        for i, m in enumerate(self.members):
            if m.status == "active":
                return i
        done = sum(1 for m in self.members if m.status == "done")
        return min(done, max(0, len(self.members) - 1))

    def public_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "lead": self.lead,
            "count": len(self.members),
            "members": [m.public_dict() for m in self.members],
        }

    def mark_active(self, index: int, note: str = "") -> None:
        for i, m in enumerate(self.members):
            if i < index:
                m.status = "done"
            elif i == index:
                m.status = "active"
                if note:
                    m.note = note
            else:
                if m.status != "done":
                    m.status = "queued"

    def mark_all_done(self) -> None:
        for m in self.members:
            m.status = "done"


def _role(slug: str) -> AgentRole | None:
    return CATALOG.get(slug)


def build_swarm(plan: Plan, text: str = "") -> SwarmPlan:
    """Assemble a small specialist squad from the action + role catalog."""
    assigned = assign_roles(plan)
    slugs: list[str] = [assigned.primary.slug]
    for extra in _ACTION_SPECIALISTS.get(plan.action or "", []):
        if extra not in slugs:
            slugs.append(extra)
    for rev in assigned.reviewers:
        if rev.slug not in slugs:
            slugs.append(rev.slug)

    # Intent keywords expand the squad slightly
    low = (text or plan.summary or "").lower()
    if any(w in low for w in ("security", "ban", "hack", "leak", "token")):
        for s in ("safety-reviewer", "privacy-guardian"):
            if s not in slugs:
                slugs.append(s)
    if any(w in low for w in ("channel", "post", "announce")):
        if "channel-editor" not in slugs:
            slugs.append("channel-editor")
    if any(w in low for w in ("deploy", "host", "server", "restart")):
        for s in ("service-operator", "release-manager", "incident-responder"):
            if s not in slugs:
                slugs.append(s)

    members: list[SwarmMember] = []
    for slug in slugs[:6]:
        role = _role(slug)
        if role:
            members.append(SwarmMember(role=role, status="queued"))

    if not members:
        members.append(SwarmMember(role=assigned.primary, status="active"))
    else:
        members[0].status = "active"
        members[0].note = "Lead specialist"

    swarm = SwarmPlan(members=members, lead=assigned.primary.name)
    # Attach for downstream public_team_summary compatibility
    if isinstance(plan.args, dict):
        plan.args["_agent_swarm"] = swarm.public_dict()
        plan.args["_agent_team"] = {
            "mode": "swarm",
            "reviewed_count": len(members),
            "members": [
                {
                    "role": m.role.name,
                    "division": m.role.division,
                    "summary": m.role.deliverable,
                    "missing": [],
                    "requires_confirmation": False,
                }
                for m in members
            ],
        }
    return swarm


def swarm_live_blocks(
    swarm: SwarmPlan,
    *,
    status: str = "Coordinating specialists…",
    phase: str = "plan",
) -> list[dict[str, Any]]:
    """tg-thinking + multi-agent progress card for streaming drafts."""
    stages = swarm.stages()
    blocks = live_action(
        status,
        stages=stages,
        active_index=swarm.active_index(),
        phase=phase,
    )
    # Agent roster table
    rows = [["Agent", "Division", "Status"]]
    for m in swarm.members:
        icon = {"done": "✅", "active": "🔄", "queued": "⏳", "blocked": "⛔"}.get(m.status, "⏳")
        rows.append([m.role.name[:22], m.role.division[:14], f"{icon} {m.status}"])
    blocks.append(table(rows, compact=True, caption="Agent swarm"))
    return blocks


def swarm_final_card(swarm: SwarmPlan, plan: Plan) -> list[dict[str, Any]]:
    """Final rich message card after specialists complete."""
    swarm.mark_all_done()
    rows = [["Agent", "Deliverable"]]
    for m in swarm.members:
        rows.append([m.role.name[:22], m.role.deliverable[:40]])
    blocks: list[dict[str, Any]] = [
        heading("Agent swarm complete", 3),
        paragraph(f"Lead: {swarm.lead} · {len(swarm.members)} specialists"),
        table(rows, compact=True, caption="Team"),
        paragraph([
            "Risk: ",
            rich_text_button(str(plan.risk), callback_data="noop:risk", style="link"),
            " · Action: ",
            rich_text_button(str(plan.action or "none")[:32], callback_data="noop:action", style="link"),
        ]),
    ]
    return blocks


def enrich_plan_with_swarm(plan: Plan, text: str = "") -> tuple[Plan, SwarmPlan]:
    """Attach swarm metadata and public stages without changing the action."""
    swarm = build_swarm(plan, text)
    # Public stages visible in confirmation cards
    extra = [f"{m.role.name}: {m.role.deliverable}" for m in swarm.members[:4]]
    # plan.public_stages may be a method — we only enrich args
    return plan, swarm
