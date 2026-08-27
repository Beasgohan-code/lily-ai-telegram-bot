# Media and File Skill

Lily can inspect, rename, compress, encode, create, and stream files inside its configured work and download directories. It sanitizes filenames, preserves extensions where appropriate, applies explicit file-size limits, uses bounded concurrent processing, and removes failed temporary outputs.

Automatic rename templates support title, season, episode, quality, and extension placeholders. FFprobe inspection reports metadata without mutating the file. Encoding and compression queue jobs remain persistent and owner-bound. Streaming links are signed, expiring, and database-backed so a separate FastAPI service can resolve them after bot restarts.

Direct downloads are disabled by default. A direct chapter file requires an already-tracked title, a direct HTTPS source from the host allow-list, explicit distribution-rights confirmation, an approved PDF/ZIP/CBZ MIME type, a bounded size, administrator approval, and a final confirmation. Lily must not scrape protected sites or bypass access controls.

## Rights-aware chapter distribution queue

After the required source and rights checks succeed, Lily creates an owner-bound persistent job instead of retrieving the file inline. The job moves through `queued`, `running`, `completed`, `failed`, or `cancelled` states. Its progress describes only operational milestones, such as validation, retrieval, delivery, or a concise failure; it must not expose credentials, signed URLs, private reasoning, or unrestricted remote details.

The requester can inspect or cancel only their own job. A queue record includes the approved action plan and outcome metadata, while a separate audit entry records the tracked title, chapter identifier, and source host. Jobs are deliberately one approved direct file at a time. A multi-file collection must arrive as a reviewed, rights-cleared manifest from an approved publisher or owner; Lily must not turn a title range into a third-party scraping operation.
