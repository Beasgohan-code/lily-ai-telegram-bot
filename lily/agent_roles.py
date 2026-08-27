"""Curated role cards and bounded handoffs for Lily's single accountable agent.

Roles improve planning and user-visible workflow clarity. They are not separate
untrusted processes, do not grant new tools, and never bypass the central Plan
risk, confirmation, ownership, or capability checks.
"""
from __future__ import annotations

from dataclasses import dataclass

from .agent import Plan


@dataclass(frozen=True)
class AgentRole:
    slug: str
    name: str
    division: str
    mission: str
    deliverable: str


@dataclass(frozen=True)
class RoleAssignment:
    primary: AgentRole
    reviewers: tuple[AgentRole, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "primary": {"name": self.primary.name, "division": self.primary.division, "deliverable": self.primary.deliverable},
            "reviewers": [{"name": role.name, "division": role.division, "deliverable": role.deliverable} for role in self.reviewers],
            "handoff_policy": "All roles propose or verify within Lily’s existing action and approval controls; no role can execute a new tool.",
        }

    def public_stages(self) -> list[str]:
        values = [f"{self.primary.name}: {self.primary.deliverable}"]
        values.extend(f"{role.name}: {role.deliverable}" for role in self.reviewers)
        return values


_ROLES = (
    AgentRole("orchestrator", "Lily Orchestrator", "coordination", "Select the smallest safe workflow.", "Action plan and public task stages"),
    AgentRole("safety-reviewer", "Safety Reviewer", "assurance", "Validate approvals, targets, and capability limits.", "Risk and confirmation check"),
    AgentRole("privacy-guardian", "Privacy Guardian", "assurance", "Minimize sensitive data in replies, logs, and artifacts.", "Redacted output check"),
    AgentRole("code-creator", "Code Creator", "engineering", "Create bounded, isolated source projects.", "Source workspace and ZIP artifact"),
    AgentRole("backend-architect", "Backend Architect", "engineering", "Design dependable server and data boundaries.", "API and data-flow recommendation"),
    AgentRole("frontend-builder", "Mini App Builder", "engineering", "Plan responsive Mini App experiences.", "UI implementation plan"),
    AgentRole("code-reviewer", "Code Reviewer", "engineering", "Check changes for correctness and maintainability.", "Review findings"),
    AgentRole("test-engineer", "Test Engineer", "quality", "Turn behavior into repeatable verification.", "Regression test plan"),
    AgentRole("release-manager", "Release Manager", "quality", "Coordinate a verified release boundary.", "Validation and release summary"),
    AgentRole("incident-responder", "Incident Responder", "operations", "Contain runtime failures with evidence.", "Safe incident status"),
    AgentRole("service-operator", "Service Operator", "operations", "Operate explicitly allowed supervised services.", "Scoped service status"),
    AgentRole("media-engineer", "Media Engineer", "media", "Inspect, rename, encode, and package permitted media.", "Bounded media result"),
    AgentRole("streaming-engineer", "Streaming Engineer", "media", "Create authorized signed streaming links.", "Scoped signed link"),
    AgentRole("channel-editor", "Channel Editor", "content", "Draft structured channel posts.", "Reviewable post draft"),
    AgentRole("community-moderator", "Community Moderator", "community", "Apply group rules consistently.", "Reviewable moderation action"),
    AgentRole("research-scout", "Research Scout", "research", "Find bounded public web information.", "Cited search results"),
    AgentRole("knowledge-curator", "Knowledge Curator", "research", "Organize reusable skills and notes.", "Structured skill or note"),
    AgentRole("data-analyst", "Data Analyst", "analysis", "Summarize bounded operational data.", "Concise status insight"),
    AgentRole("product-manager", "Product Manager", "product", "Clarify scope, outcomes, and open decisions.", "Prioritized work plan"),
    AgentRole("ux-reviewer", "UX Reviewer", "product", "Reduce friction in user-facing workflows.", "Usability recommendations"),
    AgentRole("documentation-writer", "Documentation Writer", "communication", "Explain supported behavior accurately.", "Operator or user documentation"),
    AgentRole("accessibility-reviewer", "Accessibility Reviewer", "quality", "Check interaction and readability constraints.", "Accessibility checklist"),
    AgentRole("localization-reviewer", "Localization Reviewer", "communication", "Keep language and format consistent.", "Localized response guidance"),
    AgentRole("skill-steward", "Skill Steward", "automation", "Design approved trigger rules and cooldowns.", "Guarded skill configuration"),
    AgentRole("queue-coordinator", "Queue Coordinator", "automation", "Track durable media and project jobs.", "Job status and queue update"),
    AgentRole("anime-metadata-editor", "Anime Metadata Editor", "content", "Normalize attribution-aware metadata posts.", "Structured announcement draft"),
    AgentRole("manga-tracker", "Series Tracker", "content", "Maintain user-approved title tracking.", "Tracked-series update"),
)

CATALOG = {role.slug: role for role in _ROLES}

_ACTION_ROLE = {
    "create_code_project": "code-creator", "code_project_status": "queue-coordinator", "cancel_code_project": "queue-coordinator",
    "rename_file": "media-engineer", "compress_file": "media-engineer", "encode_media": "media-engineer", "media_info": "media-engineer",
    "stream_link": "streaming-engineer", "start_channel_post": "channel-editor", "publish_channel_post": "channel-editor", "delete_last_post": "channel-editor",
    "web_search": "research-scout", "mangadex_search": "anime-metadata-editor", "mangadex_feed": "manga-tracker",
    "track_series": "manga-tracker", "list_tracked_series": "manga-tracker", "update_tracked_series": "manga-tracker",
    "create_skill": "skill-steward", "list_skills": "skill-steward", "skill_status": "skill-steward",
    "queue_status": "queue-coordinator", "queue_list": "queue-coordinator", "cancel_queue_job": "queue-coordinator",
    "register_managed_project": "service-operator", "provision_managed_project": "service-operator", "project_env_schema": "service-operator", "project_run_profiles": "service-operator",
    "generate_image": "channel-editor", "generate_video": "media-engineer", "create_file": "documentation-writer",
}

_MODERATION_ACTIONS = {"ban_user", "unban_user", "kick_user", "mute_user", "unmute_user", "restrict_user", "unrestrict_user", "demote_user", "promote_user", "delete_message", "purge_messages", "warn_user", "add_filter", "remove_filter", "set_lock", "set_group_rules", "set_welcome", "set_goodbye", "set_verification", "configure_group_control", "configure_warning_escalation", "approve_join_request", "decline_join_request"}


def catalog() -> list[dict[str, str]]:
    return [{"slug": role.slug, "name": role.name, "division": role.division, "mission": role.mission, "deliverable": role.deliverable} for role in _ROLES]


def assign_roles(plan: Plan) -> RoleAssignment:
    primary = CATALOG[_ACTION_ROLE.get(plan.action, "orchestrator")]
    reviewers: list[AgentRole] = []
    if plan.action in _MODERATION_ACTIONS:
        primary = CATALOG["community-moderator"]
    if plan.risk != "safe" or plan.requires_confirmation:
        reviewers.append(CATALOG["safety-reviewer"])
    if plan.action in {"create_code_project", "create_file", "register_managed_project", "provision_managed_project"}:
        reviewers.append(CATALOG["privacy-guardian"])
    if plan.action in {"create_code_project", "set_chat_title", "set_chat_description"}:
        reviewers.append(CATALOG["test-engineer"])
    unique = tuple(dict.fromkeys(reviewers))
    return RoleAssignment(primary, unique)
