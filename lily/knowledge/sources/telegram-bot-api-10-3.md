# Telegram Bot API 10.3 Capability Notes

Lily was checked against Telegram’s official Bot API reference and changelog on August 27, 2026. The current Bot API documentation records Bot API **10.3** on August 24, 2026.[1] [2]

## Rich messages and streaming drafts

Rich Messages support structured blocks including section headings, paragraphs, preformatted text, lists, block quotations, pull quotations, details, tables, media, and thinking/progress. Bot API 10.3 adds rich message and text buttons, a buttons block, compact tables, expandable block quotations, rich document blocks, and document links in rich messages.[1]

`sendRichMessageDraft` streams partial rich messages and Bot API 10.3 adds `can_stop` and `keep_on_stop`. Lily should use a visible **status/progress** summary only. It must never expose private model chain-of-thought, prompts, credentials, hidden tool instructions, or unverified actions as “thinking.” The bot must also handle `stopped_message_generation` updates as user-directed cancellation when draft streaming is enabled.[1]

## Previews, buttons, and private interactions

Bot API 10.3 adds disabled inline buttons and `force_reply` fields. Bot API 10.2 adds Ephemeral Messages and edit/delete methods for a one-user-plus-bot interaction in a group. They can be used for sensitive operational previews when the deployment’s Bot API implementation supports them; the normal, universally safer fallback is a requester-owned confirmation callback with a redacted status card.[1]

## Message limits and delivery

The standard `sendMessage` parameter documents a text length of **1–4096 characters after entities parsing**. Lily should not assume an 8,000-character single-message limit. It must chunk long plain-text output safely and use rich-message blocks or attached documents for larger structured material. The existing long-message sender should split at sane boundaries and retain order.[1]

## Additional current capabilities relevant to Lily

| Bot API feature | Lily opportunity | Guardrail |
|---|---|---|
| Rich document / media blocks | Attach a verified generated file or a Lily-managed file to a rich response | Never point to untrusted source files or arbitrary host paths. |
| Expandable quotations / details | Put audits, source provenance, and technical diagnostics behind user-expanded sections | Keep secrets and private action arguments out entirely. |
| Draft stop updates | Let a requester cancel an ongoing answer or preview | Cancellation must be owner-bound and not cancel unrelated work. |
| Ephemeral messages | Reduce group exposure for personal status, confirmation, or diagnostics | Use only after live Bot API compatibility testing; preserve normal confirmation fallback. |
| Managed bot updates | Observe changes to managed bot ownership/token as allowed by Telegram | Never log tokens or automatically trust a changed owner. |
| Communities / join events | Offer optional community-aware welcome and moderation signals | Require explicit group policy and administrator rights. |

## Local Bot API server

Telegram documents that a Local Bot API Server can download files without a size limit, upload up to 2000 MB, use local file paths, accept HTTP or local-IP webhooks, and increase webhook connection limits. Lily needs this architecture for large permitted rename, encode, and delivery work. The bot must still run as an unprivileged service user and keep the Local Bot API endpoint private.[1]

## References

[1]: https://core.telegram.org/bots/api "Telegram Bot API reference"
[2]: https://core.telegram.org/bots/api-changelog "Telegram Bot API changelog"
