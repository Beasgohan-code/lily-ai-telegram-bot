"""RAG and knowledge failure diagnostics (P01–P12 pattern taxonomy)."""

from __future__ import annotations

import re
from typing import Any


_PATTERNS: dict[str, dict[str, str]] = {
    "P01": {"name": "Grounding drift", "symptom": "Answer ignores bundled operating policy", "fix": "Re-route to the correct knowledge collection and tighten the request scope."},
    "P02": {"name": "Stale skill excerpt", "symptom": "Skill text is truncated or outdated relative to the live action catalog", "fix": "Refresh the bundled SKILL.md or ask Lily to show operating skills."},
    "P03": {"name": "Router misalignment", "symptom": "Wrong knowledge collection selected for the request topic", "fix": "Name the domain explicitly (moderation, media, deployment) in your message."},
    "P04": {"name": "Over-broad retrieval", "symptom": "Too many unrelated skill excerpts injected into planning", "fix": "Ask a narrower question or use a scenario runbook to focus the workflow."},
    "P05": {"name": "Missing collection", "symptom": "No bundled skill matches the topic", "fix": "Use web search for external facts; use Lily actions for operational tasks."},
    "P06": {"name": "Action/knowledge mismatch", "symptom": "Knowledge suggests behavior Lily cannot execute", "fix": "Check tool capabilities — Lily only runs named, allow-listed actions."},
    "P07": {"name": "Confirmation bypass attempt", "symptom": "User expects auto-execution from knowledge text alone", "fix": "Risky actions still require explicit Yes/No confirmation in Telegram."},
    "P08": {"name": "Session context leak", "symptom": "Old chat memory skews routing or planning", "fix": "Ask Lily to forget memory or start a fresh scoped request."},
    "P09": {"name": "Provider outage masked", "symptom": "Heuristic fallback hides model routing failures", "fix": "Run model status and check provider cooldowns."},
    "P10": {"name": "Citation gap", "symptom": "Research answer lacks sources", "fix": "Use deep research mode or web search for cited results."},
    "P11": {"name": "Team review timeout", "symptom": "Specialist memos unavailable; plan proceeds without review", "fix": "Increase LILY_AGENT_TEAM_TIMEOUT or retry when providers are healthy."},
    "P12": {"name": "Quota throttling", "symptom": "Requests fail before planning completes", "fix": "Check usage limits or ask an admin to adjust chat quotas."},
}


def diagnose(text: str, *, used_collections: list[str] | None = None, had_provider_error: bool = False, had_quota_error: bool = False, team_review_failed: bool = False) -> list[dict[str, Any]]:
    low = text.lower()
    hits: list[str] = []
    if had_quota_error:
        hits.append("P12")
    if had_provider_error:
        hits.append("P09")
    if team_review_failed:
        hits.append("P11")
    if any(word in low for word in ("wrong", "incorrect", "bad answer", "not what i asked", "hallucinat")):
        hits.append("P01")
    if any(word in low for word in ("citation", "source", "link", "prove")):
        hits.append("P10")
    if any(word in low for word in ("forget", "earlier", "previous", "still talking about")):
        hits.append("P08")
    if used_collections is not None and not used_collections:
        hits.append("P05")
    if used_collections is not None and len(used_collections) > 2:
        hits.append("P04")
    if not hits:
        hits.append("P03")
    unique = list(dict.fromkeys(hits))[:4]
    return [{"code": code, **_PATTERNS[code]} for code in unique if code in _PATTERNS]


def public_report(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "No diagnostic patterns matched."
    lines = ["**Knowledge diagnostics**"]
    for item in findings:
        lines.append(f"• **{item['code']} — {item['name']}**")
        lines.append(f"  Symptom: {item['symptom']}")
        lines.append(f"  Suggested fix: {item['fix']}")
    return "\n".join(lines)
