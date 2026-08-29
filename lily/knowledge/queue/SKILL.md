# Persistent Job Queue Skill

Lily uses a persistent, owner-bound queue for resource-intensive work such as media encoding and rights-cleared chapter-file delivery. A job begins as `queued`, becomes `running` only when a worker starts it, and finishes as `completed`, `failed`, or `cancelled`. Jobs store a bounded action plan, timestamps, progress label, and concise error. They never store raw credentials, private provider messages, unrestricted URLs, or internal reasoning traces.

## Ownership and cancellation

Only the Telegram user who created a queue job can view its detailed status or request its cancellation. Group administrators can apply their group policy, but they cannot use queue controls to impersonate another user. Cancellation changes the persistent state before the worker task is cancelled, so a worker that wakes later does not restart a cancelled job.

## Progress protocol

Progress is operational, concrete, and safe to display in rich Telegram messages. Examples include **queued for worker**, **checking approved source**, **retrieving direct file**, **processing output**, **uploading result**, **delivered**, and **failed**. Lily must not present fake percent-complete values when the upstream server provides no reliable byte count. It should report known milestones instead.

| Job type | Preflight | Worker stages | Completion evidence |
|---|---|---|---|
| Rename | Input file and safe target name | Download, rename, upload | Returned file name |
| Encode | Input file, output format, size quota | Download, FFmpeg, upload | Output path and media metadata |
| Stream | Input file and signing policy | Resolve file, create token | Expiring signed URL metadata |
| Approved chapter file | Tracked title, rights, host allow-list, MIME policy | Retrieve, validate size/type, deliver | Delivery result and audit event |

## Retry and recovery

The current worker reports a failed job rather than retrying indefinitely. A future retry controller should accept only a bounded retry count, exponential delay, and idempotent source/download conditions. It must never retry a job that was cancelled, whose source allow-list changed, whose rights attestation is absent, or whose file has already been delivered. On application restart, the operator should inspect previously `running` jobs and explicitly choose whether to mark them failed, recover from a verified checkpoint, or requeue them through a documented recovery process.

## Capacity limits

The worker count follows `LILY_MAX_CONCURRENT_JOBS`. Operators must set disk quotas high enough for both the source and output file and should reserve enough capacity for the active jobs plus failed-file cleanup. A large job should not block moderation, confirmations, or short AI responses. Queue health is visible through Lily’s status actions and audits.
