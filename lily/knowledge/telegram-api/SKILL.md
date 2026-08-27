# Telegram Bot API 10.3 Rich Delivery Skill

Lily uses Rich Messages when the deployed Bot API supports them and gracefully falls back to HTML `sendMessage` formatting when it does not. Rich responses may use headings, compact tables, details, block quotations, expandable quotations, documents, media, and styled buttons. Bot API 10.3 adds rich buttons, rich button blocks, expandable quotations, document blocks, compact-table support, generation-stop controls for drafts, and disabled buttons.[1]

## Live preview and “AI thinking” policy

Lily’s live preview is an optional `sendRichMessageDraft` status card with a short summary and public procedural stages. It can say **validating permissions**, **waiting for confirmation**, **preparing output**, or **delivering a file**. It must never expose chain-of-thought, hidden prompts, provider reasoning, secret values, raw tool arguments, or private moderation data. The user can stop a draft when Bot API support is available; the normal confirmation card remains the compatibility fallback.[1]

## Long messages and documents

`sendMessage` text is limited to 1–4096 characters after entity parsing, so Lily uses 3,500-character pages and chooses paragraph, sentence, newline, or word boundaries. Lily must preserve order and show page numbers. Large structured output should be sent as a generated document or rich document block only after source and permission checks; it must not be lost by string truncation.[1]

## Local Bot API server

For permitted large-file work, Lily’s Local Bot API deployment can download without a file-size limit and upload files up to 2,000 MB. The local API endpoint must stay on private networking, and the Lily service must run as an unprivileged user with narrow filesystem access.[1]

## References

[1]: https://core.telegram.org/bots/api "Telegram Bot API reference and current Bot API 10.3 changes"
