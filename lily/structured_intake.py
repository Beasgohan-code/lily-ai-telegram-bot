"""Structured intake packets for moderation, deployment, and research requests."""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class IntakePacket:
    intake_id: str
    kind: str
    requester_id: int
    chat_id: int
    summary: str
    fields: dict[str, Any] = field(default_factory=dict)
    blocking: list[str] = field(default_factory=list)
    created_at: int = field(default_factory=lambda: int(time.time()))

    def public_dict(self) -> dict[str, Any]:
        return {
            "intake_id": self.intake_id[:12],
            "kind": self.kind,
            "summary": self.summary[:500],
            "fields": {str(k): str(v)[:300] for k, v in self.fields.items()},
            "blocking": self.blocking[:8],
            "complete": not self.blocking,
        }


def create_intake(kind: str, text: str, requester_id: int, chat_id: int, context: dict[str, Any] | None = None) -> IntakePacket:
    context = context or {}
    intake_id = uuid.uuid4().hex
    low = text.lower()
    fields: dict[str, Any] = {}
    blocking: list[str] = []
    if kind == "moderation":
        fields["reason"] = _extract_after(text, ("report", "because", "for"))[:500]
        fields["target_user_id"] = context.get("target_user_id") or context.get("reply", {}).get("user_id")
        if not fields.get("target_user_id"):
            blocking.append("Identify the member (reply or user ID)")
        if not fields.get("reason"):
            blocking.append("Describe the moderation reason")
        summary = f"Moderation intake: {fields.get('reason') or 'pending details'}"
    elif kind == "deployment":
        url = next(iter(re.findall(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", text)), "")
        slug_match = re.search(r"(?:project|bot)\s+([a-z][a-z0-9-]{1,62})", low)
        fields["repository_url"] = url
        fields["slug"] = slug_match.group(1) if slug_match else ""
        if not url:
            blocking.append("Provide the GitHub repository URL")
        if not fields["slug"]:
            blocking.append("Provide a project slug/name")
        summary = f"Deployment intake: {fields.get('slug') or 'new project'}"
    else:
        fields["question"] = text.strip()[:1000]
        if len(fields["question"]) < 8:
            blocking.append("Provide a clearer research question")
        summary = f"Research intake: {fields['question'][:120]}"
    return IntakePacket(intake_id=intake_id, kind=kind, requester_id=requester_id, chat_id=chat_id, summary=summary, fields=fields, blocking=blocking)


def detect_kind(text: str) -> str | None:
    low = text.lower()
    if any(word in low for word in ("report user", "moderation intake", "open a case", "file a report")):
        return "moderation"
    if any(word in low for word in ("deploy intake", "deployment intake")):
        return "deployment"
    if any(word in low for word in ("research intake", "deep research", "investigate")):
        return "research"
    return None


def _extract_after(text: str, markers: tuple[str, ...]) -> str:
    for marker in markers:
        match = re.search(rf"{marker}\s*[:,-]?\s*(.+)$", text, re.I | re.S)
        if match:
            return match.group(1).strip()
    return text.strip()
