"""NEXUS-style scenario runbooks adapted for Lily's bounded agent workflow.

Inspired by agency orchestration patterns: phased teams, activation gates, and
explicit deliverables — without importing external prompts or granting new tools.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScenarioPhase:
    name: str
    goal: str
    deliverable: str
    roles: tuple[str, ...]


@dataclass(frozen=True)
class ScenarioRunbook:
    slug: str
    title: str
    mode: str
    summary: str
    duration: str
    phases: tuple[ScenarioPhase, ...]

    def public_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "title": self.title,
            "mode": self.mode,
            "summary": self.summary,
            "duration": self.duration,
            "phases": [
                {"name": phase.name, "goal": phase.goal, "deliverable": phase.deliverable, "roles": list(phase.roles)}
                for phase in self.phases
            ],
        }


_RUNBOOKS: tuple[ScenarioRunbook, ...] = (
    ScenarioRunbook(
        slug="startup-mvp",
        title="Startup MVP Build",
        mode="NEXUS-Sprint",
        summary="Idea to live product with real users — without skipping QA.",
        duration="4–6 weeks",
        phases=(
            ScenarioPhase("Discover", "Clarify scope, users, and success metrics", "Prioritized MVP brief", ("product-manager", "research-scout", "ux-reviewer")),
            ScenarioPhase("Scaffold", "Define architecture and delivery boundaries", "Technical scaffold plan", ("backend-architect", "frontend-builder", "code-creator")),
            ScenarioPhase("Build", "Implement core flows with bounded iterations", "Working feature slice", ("code-creator", "test-engineer", "code-reviewer")),
            ScenarioPhase("Harden", "Security, privacy, and regression checks", "Release gate summary", ("privacy-guardian", "safety-reviewer", "release-manager")),
            ScenarioPhase("Launch", "Ship with operator documentation", "Launch checklist", ("documentation-writer", "channel-editor", "service-operator")),
        ),
    ),
    ScenarioRunbook(
        slug="incident-response",
        title="Incident Response",
        mode="NEXUS-Micro",
        summary="Contain, diagnose, and recover from a live service incident.",
        duration="Hours to days",
        phases=(
            ScenarioPhase("Triage", "Assess blast radius and user impact", "Incident severity card", ("incident-responder", "service-operator", "data-analyst")),
            ScenarioPhase("Contain", "Stop bleeding and preserve evidence", "Containment actions", ("incident-responder", "safety-reviewer", "privacy-guardian")),
            ScenarioPhase("Diagnose", "Identify root cause with bounded evidence", "Root-cause hypothesis", ("service-operator", "test-engineer", "research-scout")),
            ScenarioPhase("Recover", "Restore service with verified rollback path", "Recovery summary", ("release-manager", "documentation-writer", "queue-coordinator")),
            ScenarioPhase("Postmortem", "Capture lessons and prevention tasks", "Postmortem draft", ("documentation-writer", "product-manager", "safety-reviewer")),
        ),
    ),
    ScenarioRunbook(
        slug="content-launch",
        title="Content & Channel Launch",
        mode="NEXUS-Sprint",
        summary="Plan, draft, review, and publish a channel or community launch.",
        duration="1–2 weeks",
        phases=(
            ScenarioPhase("Plan", "Define audience, cadence, and assets", "Editorial calendar", ("channel-editor", "product-manager", "anime-metadata-editor")),
            ScenarioPhase("Draft", "Produce reviewable announcement content", "Rich post drafts", ("channel-editor", "documentation-writer", "localization-reviewer")),
            ScenarioPhase("Review", "Accessibility, brand, and safety checks", "Approval checklist", ("accessibility-reviewer", "safety-reviewer", "community-moderator")),
            ScenarioPhase("Publish", "Ship with attribution and audit trail", "Published announcement", ("channel-editor", "release-manager", "knowledge-curator")),
        ),
    ),
    ScenarioRunbook(
        slug="community-growth",
        title="Community Growth Sprint",
        mode="NEXUS-Sprint",
        summary="Grow engagement while keeping moderation and trust controls tight.",
        duration="2–4 weeks",
        phases=(
            ScenarioPhase("Audit", "Baseline health, rules clarity, and friction", "Community health report", ("community-moderator", "data-analyst", "ux-reviewer")),
            ScenarioPhase("Engage", "Design welcome, polls, and recurring touchpoints", "Engagement playbook", ("community-moderator", "channel-editor", "skill-steward")),
            ScenarioPhase("Protect", "Tune anti-spam, verification, and escalation", "Moderation policy update", ("community-moderator", "safety-reviewer", "privacy-guardian")),
            ScenarioPhase("Measure", "Track reports, retention signals, and queue health", "Growth dashboard summary", ("data-analyst", "queue-coordinator", "product-manager")),
        ),
    ),
    ScenarioRunbook(
        slug="deep-research",
        title="Deep Research Mission",
        mode="NEXUS-Micro",
        summary="Multi-scout research with synthesis and citations.",
        duration="Minutes to hours",
        phases=(
            ScenarioPhase("Scope", "Define question, depth, and output format", "Research brief", ("research-scout", "product-manager", "knowledge-curator")),
            ScenarioPhase("Scout", "Parallel bounded web and knowledge search", "Source packet", ("research-scout", "data-analyst", "source-verifier")),
            ScenarioPhase("Synthesize", "Merge findings with disagreement notes", "Research summary", ("documentation-writer", "fact-checker", "safety-reviewer")),
        ),
    ),
)


def catalog() -> list[dict[str, Any]]:
    return [book.public_dict() for book in _RUNBOOKS]


def get(slug: str) -> ScenarioRunbook | None:
    wanted = str(slug or "").strip().lower()
    for book in _RUNBOOKS:
        if book.slug == wanted:
            return book
    return None


def match_request(text: str) -> ScenarioRunbook | None:
    low = text.lower()
    for book in _RUNBOOKS:
        if book.slug.replace("-", " ") in low or book.title.lower() in low:
            return book
    if any(term in low for term in ("runbook", "scenario", "nexus")):
        for book in _RUNBOOKS:
            if book.slug.split("-")[0] in low:
                return book
    return None


def phase_stages(book: ScenarioRunbook, phase_index: int = 0) -> list[str]:
    index = max(0, min(phase_index, len(book.phases) - 1))
    phase = book.phases[index]
    return [
        f"Scenario: {book.title} ({book.mode})",
        f"Phase {index + 1}/{len(book.phases)} — {phase.name}",
        f"Goal: {phase.goal}",
        f"Deliverable: {phase.deliverable}",
        f"Team: {', '.join(role.replace('-', ' ').title() for role in phase.roles[:4])}",
    ]
