"""Lily's AI-first group-management control catalogue.

The catalogue is intentionally data-driven: each control has a stable key,
category, description, default state, and risk level. Chat settings decide
whether automatic controls apply; direct member-affecting actions still go
through Lily's confirmation and Telegram permission checks.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GroupControl:
    key: str
    category: str
    label: str
    description: str
    default_enabled: bool = False
    risk: str = "risky"


def _controls(category: str, values: list[tuple[str, str, str, bool, str]]) -> list[GroupControl]:
    return [GroupControl(key, category, label, description, enabled, risk) for key, label, description, enabled, risk in values]


GROUP_CONTROLS = tuple(
    _controls("Member governance", [
        ("trusted_members", "Trusted members", "Exempt selected members from automated filters.", False, "dangerous"),
        ("moderator_roles", "Moderator roles", "Use a safe, non-promotion moderator permission profile.", True, "dangerous"),
        ("custom_titles", "Custom admin titles", "Set or clear an administrator title.", False, "dangerous"),
        ("slow_mode", "Slow mode", "Set the group message interval.", False, "dangerous"),
        ("join_request_review", "Join request review", "Require Lily-assisted accept or decline decisions.", False, "dangerous"),
        ("member_restrictions", "Member restrictions", "Apply granular Telegram sending permissions.", True, "dangerous"),
        ("member_exemptions", "Member exemptions", "Record members exempt from selected automatic controls.", False, "dangerous"),
        ("staff_notifications", "Staff notifications", "Notify admins about serious automated actions.", True, "risky"),
    ])
    + _controls("Member moderation", [
        ("warn", "Warnings", "Record a rule warning against a member.", True, "risky"),
        ("warning_escalation", "Warning escalation", "Escalate repeated warnings to an approval-gated restriction.", True, "dangerous"),
        ("clear_warnings", "Clear warnings", "Remove a member’s warning history after admin approval.", False, "dangerous"),
        ("mute", "Temporary mute", "Restrict a member from sending messages for a bounded time.", True, "dangerous"),
        ("kick", "Kick", "Remove a member without retaining a ban.", True, "dangerous"),
        ("ban", "Ban", "Ban a member from the group.", True, "dangerous"),
        ("unban", "Unban", "Remove a member’s ban.", True, "dangerous"),
        ("purge", "Purge", "Delete a bounded set of recent messages after confirmation.", True, "dangerous"),
        ("pinning", "Pin messages", "Pin or unpin staff-approved announcements.", True, "dangerous"),
        ("reports", "Member reports", "Create a structured moderator report.", True, "risky"),
    ])
    + _controls("Content locks", [
        ("links", "Link lock", "Delete messages containing URLs.", False, "risky"),
        ("forwards", "Forward lock", "Delete forwarded messages.", False, "risky"),
        ("documents", "Document lock", "Delete uploaded documents.", False, "risky"),
        ("photos", "Photo lock", "Delete photos.", False, "risky"),
        ("videos", "Video lock", "Delete videos.", False, "risky"),
        ("audio", "Audio lock", "Delete audio and voice notes.", False, "risky"),
        ("animations", "GIF lock", "Delete animations and GIFs.", False, "risky"),
        ("stickers", "Sticker lock", "Delete stickers.", False, "risky"),
        ("polls", "Poll lock", "Delete polls.", False, "risky"),
        ("contacts", "Contact lock", "Delete contact cards.", False, "risky"),
        ("locations", "Location lock", "Delete locations and venues.", False, "risky"),
    ])
    + _controls("Anti-spam", [
        ("flood", "Flood control", "Restrict rapid repeated messages.", True, "risky"),
        ("duplicate_text", "Duplicate control", "Delete repeated identical messages in a short window.", False, "risky"),
        ("caps", "Caps control", "Delete mostly-uppercase spam messages.", False, "risky"),
        ("mention_spam", "Mention control", "Delete messages with excessive mentions.", False, "risky"),
        ("emoji_spam", "Emoji control", "Delete messages with excessive emoji density.", False, "risky"),
        ("domain_blocklist", "Domain blocklist", "Delete messages containing blocked domains.", False, "risky"),
        ("invite_links", "Invite link control", "Delete Telegram group/channel invite links.", False, "risky"),
        ("new_member_limits", "New member limits", "Apply stricter automatic checks to recent joiners.", False, "risky"),
        ("new_member_cooldown", "New member cooldown", "Delay selected media or link activity after a member joins.", False, "risky"),
        ("suspicious_text", "Suspicious text", "Flag suspicious scam patterns for review.", False, "risky"),
        ("media_spam", "Media flood", "Restrict repeated media uploads.", False, "risky"),
    ])
    + _controls("Rules and automations", [
        ("keyword_filters", "Keyword filters", "Run stored phrase filters with custom responses.", True, "risky"),
        ("regex_filters", "Pattern filters", "Run administrator-approved regex filters.", False, "dangerous"),
        ("saved_notes", "Saved notes", "Store and retrieve group notes.", True, "risky"),
        ("welcome", "Welcome flow", "Send an onboarding message to new members.", True, "risky"),
        ("verification", "Member verification", "Require an answer before granting normal participation.", False, "dangerous"),
        ("goodbye", "Goodbye messages", "Optionally announce departures.", False, "risky"),
        ("scheduled_posts", "Scheduled posts", "Create approval-gated recurring announcements.", False, "dangerous"),
        ("recurring_summary", "Recurring summaries", "Prepare scheduled activity and moderation summaries.", False, "risky"),
        ("inactivity_alerts", "Inactivity alerts", "Notify admins when configured activity thresholds are missed.", False, "risky"),
        ("auto_replies", "Auto replies", "Reply to configured questions or trigger words.", False, "risky"),
    ])
    + _controls("Privacy and intelligence", [
        ("memory", "Group memory", "Store selected context for later retrieval.", False, "dangerous"),
        ("memory_retention", "Memory retention", "Apply a retention period for stored memories.", False, "dangerous"),
        ("audit_log", "Audit log", "Record Lily actions and moderation events.", True, "risky"),
        ("audit_export", "Audit export", "Export an administrator-readable action history.", False, "dangerous"),
        ("case_notes", "Moderator case notes", "Attach private notes to reports and incidents.", False, "risky"),
        ("daily_digest", "Daily digest", "Summarize discussions, decisions, and unresolved items.", False, "risky"),
        ("faq_suggestions", "FAQ suggestions", "Propose answers to repeated community questions.", False, "risky"),
        ("task_extraction", "Task extraction", "Extract action items from a selected discussion.", False, "risky"),
        ("sentiment_alerts", "Sentiment alerts", "Flag escalating conflict for moderator review.", False, "risky"),
        ("web_research", "Web research", "Use web search only when explicitly requested.", True, "risky"),
    ])
)

GROUP_CONTROL_MAP = {control.key: control for control in GROUP_CONTROLS}


def control_defaults() -> dict[str, bool]:
    return {control.key: control.default_enabled for control in GROUP_CONTROLS}


def control_summary() -> dict[str, list[GroupControl]]:
    groups: dict[str, list[GroupControl]] = {}
    for control in GROUP_CONTROLS:
        groups.setdefault(control.category, []).append(control)
    return groups
