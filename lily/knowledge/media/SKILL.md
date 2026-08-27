# Media and File Skill

Lily can inspect, rename, compress, encode, create, and stream files inside its configured work and download directories. It sanitizes filenames, preserves extensions where appropriate, applies explicit file-size limits, uses bounded concurrent processing, and removes failed temporary outputs.

Automatic rename templates support title, season, episode, quality, and extension placeholders. FFprobe inspection reports metadata without mutating the file. Encoding and compression queue jobs remain persistent and owner-bound. Streaming links are signed, expiring, and database-backed so a separate FastAPI service can resolve them after bot restarts.

Direct downloads are disabled by default. A direct chapter file requires an already-tracked title, a direct HTTPS source from the host allow-list, explicit distribution-rights confirmation, an approved PDF/ZIP/CBZ MIME type, a bounded size, administrator approval, and a final confirmation. Lily must not scrape protected sites or bypass access controls.
