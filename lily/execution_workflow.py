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
    if action in {"rename_file", "compress_file", "encode_media", "media_info", "stream_link"}:
        stages.append("Check the selected file and configured size limits")
    elif action == "web_search":
        stages.append("Validate the configured search provider and request limits")
    elif action in {"download_song", "download_chapter"}:
        stages.append("Check source allow-lists, direct-file format, and declared rights")
    elif action in {"register_managed_project", "provision_managed_project"}:
        stages.append("Check repository allow-list, project isolation, and fixed runtime profile")
    elif action in {"ban_user", "kick_user", "mute_user", "restrict_user", "delete_message", "purge_messages"}:
        stages.append("Check moderator authority and the exact chat target")
    else:
        stages.append("Prepare the selected named Lily tool")
    if requires_confirmation or risk in {"risky", "dangerous"}:
        stages.append("Wait for the requester’s explicit confirmation")
    stages.extend(["Execute only the approved named action", "Record the outcome in Lily’s audit log", "Report a concise result"])
    return stages
