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

# Independent capability cards covering the practical division breadth found in
# the reviewed role taxonomies. They are concise Lily metadata, not copied
# prompts. None is mapped to a new executable action without a separate safety
# review in _ACTION_ROLE.
_ROLE_FAMILIES: dict[str, tuple[str, ...]] = {
    "engineering": ("API Platform Specialist", "Backend Reliability Specialist", "Frontend Performance Specialist", "Mobile Experience Specialist", "Developer Tooling Specialist", "Database Reliability Specialist", "Release Automation Specialist", "Identity Access Specialist", "Integration Specialist", "Architecture Reviewer"),
    "design": ("Design System Specialist", "Interaction Designer", "Visual Accessibility Specialist", "Brand Systems Specialist", "Content Design Specialist", "Research Synthesizer", "Prototype Reviewer", "Information Architect", "Interface Quality Reviewer", "Inclusive Design Specialist"),
    "product": ("Discovery Specialist", "Requirements Analyst", "Roadmap Planner", "Experiment Designer", "Feedback Synthesizer", "Metrics Strategist", "User Journey Analyst", "Feature Prioritizer", "Release Planner", "Product Operations Specialist"),
    "quality": ("Test Automation Specialist", "Regression Analyst", "API Quality Specialist", "Performance Analyst", "Evidence Reviewer", "Release Gatekeeper", "Accessibility Tester", "Data Quality Reviewer", "Reliability Analyst", "Workflow Quality Specialist"),
    "security": ("Application Security Reviewer", "Threat Modeler", "Secrets Hygiene Reviewer", "Identity Assurance Specialist", "Privacy Controls Reviewer", "Incident Triage Specialist", "Security Logging Specialist", "Dependency Risk Reviewer", "Abuse Prevention Specialist", "Secure Configuration Reviewer"),
    "operations": ("SRE Specialist", "Observability Specialist", "Capacity Planner", "Deployment Coordinator", "Incident Coordinator", "Change Manager", "Backup Reviewer", "Service Health Analyst", "Runbook Writer", "Operational Readiness Reviewer"),
    "research": ("Source Verifier", "Literature Scout", "Fact Checker", "Competitive Analyst", "Trend Analyst", "Dataset Reviewer", "Search Relevance Specialist", "Citation Curator", "Knowledge Graph Planner", "Research Brief Writer"),
    "analysis": ("Data Explorer", "Metrics Analyst", "Dashboard Planner", "Forecast Reviewer", "Experiment Analyst", "Anomaly Reviewer", "Reporting Specialist", "Data Storyteller", "Operations Analyst", "Decision Support Analyst"),
    "communication": ("Technical Editor", "Support Writer", "Release Communicator", "Community Writer", "Policy Explainer", "Documentation Maintainer", "Translation Reviewer", "Plain Language Editor", "Knowledge Base Writer", "Stakeholder Brief Writer"),
    "community": ("Community Health Analyst", "Rule Clarity Reviewer", "Moderator Coach", "Onboarding Specialist", "Escalation Coordinator", "Member Support Specialist", "Trust and Safety Reviewer", "Engagement Planner", "Feedback Listener", "Community Operations Specialist"),
    "content": ("Editorial Planner", "Announcement Writer", "Metadata Curator", "Content QA Reviewer", "Series Editor", "Publication Coordinator", "Caption Writer", "Template Designer", "Archive Curator", "Content Calendar Planner"),
    "media": ("Transcode Planner", "Media Quality Reviewer", "Asset Organizer", "Streaming Delivery Reviewer", "Captioning Planner", "Format Compatibility Specialist", "Compression Analyst", "Media Metadata Curator", "Archive Packaging Specialist", "Delivery Quality Specialist"),
    "automation": ("Workflow Designer", "Trigger Reviewer", "Queue Analyst", "Job Lifecycle Reviewer", "Integration Planner", "Scheduler Designer", "Automation QA Specialist", "Error Recovery Planner", "Process Optimizer", "Policy Automation Reviewer"),
    "strategy": ("Systems Strategist", "Risk Strategist", "Scenario Planner", "Operating Model Reviewer", "Opportunity Analyst", "Decision Framework Designer", "Portfolio Planner", "Market Context Analyst", "Change Strategy Specialist", "Strategic Brief Writer"),
    "finance": ("Cost Visibility Analyst", "Budget Guardrail Reviewer", "Unit Economics Analyst", "Procurement Analyst", "Revenue Operations Analyst", "Forecast Quality Reviewer", "Spend Anomaly Reviewer", "FinOps Planner", "Pricing Researcher", "Financial Reporting Specialist"),
    "academic": ("Research Methodologist", "Statistical Reviewer", "Historical Context Analyst", "Geography Analyst", "Anthropology Reviewer", "Narrative Analyst", "Evidence Synthesizer", "Study Planner", "Peer Review Specialist", "Academic Writing Editor"),
    "geospatial": ("Map Data Reviewer", "Location Intelligence Analyst", "Spatial Data Planner", "Route Analysis Specialist", "Geocoding Reviewer", "GIS Workflow Specialist", "Boundary Data Analyst", "Spatial Quality Reviewer", "Field Data Planner", "Geographic Context Analyst"),
    "healthcare": ("Health Information Reviewer", "Clinical Workflow Analyst", "Care Operations Analyst", "Medical Content Safety Reviewer", "Healthcare Privacy Reviewer", "Patient Communication Reviewer", "Health Data Quality Specialist", "Accessibility Care Reviewer", "Evidence Summary Specialist", "Safety Escalation Coordinator"),
    "game-development": ("Game Systems Designer", "Gameplay QA Specialist", "Narrative Design Reviewer", "Game Performance Analyst", "Level Design Planner", "Player Experience Reviewer", "Asset Pipeline Planner", "Live Operations Analyst", "Game Accessibility Reviewer", "Prototype Playtester"),
}


def _family_roles() -> tuple[AgentRole, ...]:
    generated: list[AgentRole] = []
    for division, names in _ROLE_FAMILIES.items():
        for index, name in enumerate(names, start=1):
            slug = f"{division}-{index:02d}"
            generated.append(AgentRole(slug, name, division, f"Provide a scoped {division} review within Lily’s safety boundary.", f"{name} recommendation"))
    return tuple(generated)


_ROLES = _ROLES + _family_roles()

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


def catalog(division: str | None = None) -> list[dict[str, str]]:
    wanted = str(division or "").strip().lower()
    roles = [role for role in _ROLES if not wanted or role.division == wanted]
    return [{"slug": role.slug, "name": role.name, "division": role.division, "mission": role.mission, "deliverable": role.deliverable} for role in roles]


def catalog_summary() -> list[dict[str, object]]:
    counts: dict[str, int] = {}
    for role in _ROLES:
        counts[role.division] = counts.get(role.division, 0) + 1
    return [{"division": division, "roles": count} for division, count in sorted(counts.items())]


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
