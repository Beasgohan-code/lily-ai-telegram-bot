# Lily Feature Roadmap

## Newly implemented

Lily now supports safe media inspection through a natural-language request such as `Lily show file details for this video`. The tool downloads the replied media into Lily’s managed workspace, calls FFprobe, presents format, size, duration, codec, and dimensions in a rich table, and deletes the temporary input afterward.

Admins can request `Lily export moderation history`. This action is confirmation-gated, restricted to administrators, emits a CSV document containing the retained audit records, and records the export itself as an audit event. It does not expose provider keys or arbitrary filesystem data.

Automatic renaming now accepts a reusable template from chat, for example `Lily rename uploads using template {title} - {quality}.{ext}`. Existing filename sanitization, extension preservation, managed-workspace boundaries, quotas, and confirmation gates remain active.

Signed streaming links are now stored in Lily’s SQLite database instead of process memory. This allows the bot and standalone FastAPI streaming service to share expiring links safely across restarts and separate containers.

## Recommended next upgrades

| Priority | Feature | Why it matters | Safety boundary |
|---:|---|---|---|
| 1 | Live Mini App API bridge | Expose group controls, queues, diagnostics, and approvals through the deployed dashboard. | Verify Telegram `initData`; require group-admin authorization on every mutation. |
| 2 | Rename profiles | Let each group maintain profiles such as anime, TV, movie, music, and document naming formats. | Store templates only; sanitize every output and never evaluate templates as code. |
| 3 | Moderation case dashboard | Show open reports, warnings, verification queue, and audit history in one view. | Redact private notes from ordinary members and enforce least-privilege access. |
| 4 | Anti-spam scoring | Combine flood, duplicate-text, mention, link, and new-member signals into explainable scores. | Use bounded scores, trusted-member exemptions, audit events, and admin-tunable thresholds. |
| 5 | Media presets | Add named encode presets for mobile, web, archive, audio extraction, and subtitle-safe video. | Allow-list codecs, containers, and FFmpeg flags; enforce size, duration, and concurrency limits. |
| 6 | Channel post library | Save approved announcement templates and preview rendered RichMessage blocks before publishing. | Publishing and deletion remain confirmation-gated and channel-admin-only. |
| 7 | Backup and restore | Export group settings, controls, skills, filters, and audit metadata for disaster recovery. | Exclude secrets and raw media; encrypt archives and require explicit admin confirmation. |
| 8 | Provider observability | Track latency, cooldowns, error classes, and token usage by provider tier. | Store aggregate metrics by default and never persist prompts containing private media or secrets. |

## Deliberately deferred

A true batch-renaming workflow requires a durable media inventory and a clear user-selected scope. Lily should not rename every file in a group based on an ambiguous message. The safer design is an explicit queue or selected-message set with a preview, total count, estimated bytes, and one final confirmation.

A full scheduler for reminders, recurring posts, and periodic cleanup should be introduced only after the always-on runtime is selected. Those jobs need durable state, timezone handling, retry policy, and a worker process; they should not be implemented as ad-hoc polling inside a Telegram update handler.

Platform ripping or unrestricted song downloading remains intentionally excluded. Lily’s media downloader accepts only direct audio URLs from an administrator-configured allow-list and requires a rights confirmation.

## Example requests

```text
Lily show file details for this video.
Lily export moderation history.
Lily rename uploads using template {title} - S{season:02d}E{episode:02d} - {quality}.{ext}.
Lily enable the verification queue and show pending members.
Lily show group diagnostics.
Lily create poll: Should we enable archive mode? | Yes | No
```

## Current validation

The Python backend compiles successfully and the complete regression suite passes **23/23 tests**. Real Telegram execution still requires a test bot, a test group where Lily has the necessary administrator permissions, configured storage, and the selected always-on host.

*Prepared by Manus AI.*

## References

[1]: https://core.telegram.org/bots/api "Telegram Bot API"
[2]: https://ffmpeg.org/ffprobe.html "FFprobe Documentation"
[3]: https://core.telegram.org/bots/webapps "Telegram Mini Apps"
