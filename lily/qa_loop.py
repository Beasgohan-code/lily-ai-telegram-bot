"""Dev↔QA bounded retry loop for Lily code-project jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


MAX_QA_RETRIES = 3


@dataclass
class QAReview:
    passed: bool
    findings: tuple[str, ...]
    attempt: int

    def public_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "attempt": self.attempt,
            "findings": list(self.findings),
            "max_retries": MAX_QA_RETRIES,
        }


def review_project(workspace: dict[str, Any], language: str) -> QAReview:
    """Deterministic QA checks — no arbitrary code execution."""
    files = workspace.get("files") if isinstance(workspace.get("files"), dict) else {}
    findings: list[str] = []
    if not files:
        findings.append("No source files were generated.")
    for name, content in files.items():
        if not str(name).strip():
            findings.append("A file has an empty name.")
        if len(str(content)) > 500_000:
            findings.append(f"{name} exceeds the size boundary.")
        if ".." in str(name) or str(name).startswith("/"):
            findings.append(f"{name} has an invalid path.")
    lang = str(language or "python").lower()
    if lang == "python" and files and not any(name.endswith(".py") for name in files):
        findings.append("Python project is missing a .py entry file.")
    if lang in {"javascript", "typescript"} and files and not any(name.endswith((".js", ".ts", ".tsx")) for name in files):
        findings.append("JavaScript/TypeScript project is missing a source file.")
    readme_present = any("readme" in name.lower() for name in files)
    if len(files) >= 2 and not readme_present:
        findings.append("Consider adding a README for maintainability.")
    passed = not any("missing" in item.lower() or "invalid" in item.lower() or "No source" in item for item in findings)
    return QAReview(passed=passed, findings=tuple(findings[:6]), attempt=1)


def apply_retry_feedback(workspace: dict[str, Any], review: QAReview) -> dict[str, Any]:
    """Annotate workspace metadata with QA feedback for the next attempt."""
    updated = dict(workspace)
    updated["_qa"] = review.public_dict()
    return updated


def should_escalate(attempt: int, review: QAReview) -> bool:
    return attempt >= MAX_QA_RETRIES and not review.passed
