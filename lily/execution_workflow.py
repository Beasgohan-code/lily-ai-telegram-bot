"""Public execution-stage descriptions for Lily plans.

These stages are procedural status labels, not hidden model reasoning. They
provide users with a clear account of the checks Lily will perform before and
after a named action.
"""

from __future__ import annotations


def visible_stages(action: str, risk: str, missing: list[str], requires_confirmation: bool) -> list[str]:
    if missing:
        return ["Understand the request", "Collect the missing details", "Validate the target and permissions", "Prepare a safe action plan"]
    stages = ["Understand the request", "Validate target, permissions, and capability gates"]
    if action in {"rename_file", "compress_file", "encode_media", "media_info", "stream_link", "generate_speech"}:
        stages.append("Check the selected file and configured size limits")
    elif action == "create_code_project":
        stages.append("Create an isolated source workspace and validate its file boundaries")
        stages.append("Package the generated source files for delivery")
    elif action == "web_search":
        stages.append("Validate the configured search provider and request limits")
    elif action in {"download_song", "download_chapter"}:
        stages.append("Check source allow-lists, direct-file format, and declared rights")
    elif action in {"register_managed_project", "provision_managed_project"}:
        stages.append("Check repository allow-list, project isolation, and fixed runtime profile")
    elif action == "deep_research":
        stages.append("Launch parallel research scouts with bounded web search")
        stages.append("Synthesize cited findings into a concise summary")
    elif action == "run_scenario":
        stages.append("Load the selected NEXUS scenario runbook and phase roster")
        stages.append("Show public phase goals, deliverables, and specialist roles")
    elif action in {"rag_debug", "admin_briefing", "show_handoff", "start_intake", "show_intake", "list_scenarios"}:
        stages.append("Prepare a read-only operational or diagnostic report")
    elif action in {"ban_user", "kick_user", "mute_user", "restrict_user", "delete_message", "purge_messages"}:
        stages.append("Check moderator authority and the exact chat target")
    elif action in {"set_group_default_permissions", "create_invite_link", "revoke_invite_link", "create_forum_topic", "close_forum_topic", "reopen_forum_topic", "delete_forum_topic", "list_administrators", "group_member_count", "send_group_announcement", "post_checklist", "unpin_all_messages", "set_chat_sticker_set", "delete_chat_sticker_set"}:
        stages.append("Check administrator authority and the exact group scope")
    else:
        stages.append("Prepare the selected named Lily tool")
    if requires_confirmation or risk in {"risky", "dangerous"}:
        stages.append("Wait for the requester’s explicit confirmation")
    stages.extend(["Execute only the approved named action", "Record the outcome in Lily’s audit log", "Report a concise result"])
    return stages
