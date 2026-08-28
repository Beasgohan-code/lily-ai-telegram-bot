# Telegram Bot API 10.3 Rich Delivery Skill

Lily uses Rich Messages when the deployed Bot API supports them and gracefully falls back to HTML `sendMessage` formatting when it does not. Rich responses may use headings, compact tables, details, block quotations, expandable quotations, documents, media, and styled buttons. Bot API 10.3 adds rich buttons, rich button blocks, expandable quotations, document blocks, compact-table support, generation-stop controls for drafts, and disabled buttons.[1]

## Live preview, drafts, and AI thinking

Lily uses Bot API 10.3 draft methods for professional, low-noise updates:

| Method | Use |
|---|---|
| `sendRichMessageDraft` | Structured status cards with thinking blocks and stages |
| `sendMessageDraft` | Lightweight text fallback when rich drafts are unavailable |

Live drafts show **public** status only: validating, thinking, awaiting confirmation, delivering. They never expose chain-of-thought, prompts, credentials, or private moderation data. Users can stop generation when the Bot API supports `can_stop`; Lily records the stop and does not continue the action.

Set `LILY_COMPACT_RESPONSES=true` (default) to avoid duplicate progress messages in chat. Set `LILY_ENABLE_AI_THINKING=true` to show the official Rich Message thinking indicator while Lily plans or answers.

## Long messages and documents

`sendMessage` text is limited to 1–4096 characters after entity parsing, so Lily uses 3,500-character pages and chooses paragraph, sentence, newline, or word boundaries. Lily must preserve order and show page numbers. Large structured output should be sent as a generated document or rich document block only after source and permission checks; it must not be lost by string truncation.[1]

## Local Bot API server

For permitted large-file work, Lily’s Local Bot API deployment can download without a file-size limit and upload files up to 2,000 MB. The local API endpoint must stay on private networking, and the Lily service must run as an unprivileged user with narrow filesystem access.[1]

## References

[1]: https://core.telegram.org/bots/api "Telegram Bot API reference and current Bot API 10.3 changes"
