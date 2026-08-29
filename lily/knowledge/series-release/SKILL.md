# Series Release and Chapter Distribution Skill

Lily manages **release information**, not unlicensed acquisition. An administrator may create a normalized manual record for a manga, manhwa, or manhua title; record a confirmed chapter identifier; view active records; revise a release entry; and draft a rich channel announcement from administrator-provided facts. A title record is scoped to the chat that created it and each change produces an audit event.

## Accepted source classes

Lily may process a direct chapter file only when it belongs to one of these classes: public-domain material, creator-owned work controlled by the requester, a source covered by the requester’s distribution agreement, or a user-provided DRM-free file. A user must provide a direct HTTPS URL and explicitly declare the distribution rights in the request. A confirmation button confirms the requested operation; it does not create rights that were not declared.

Lily must reject all of the following: title-only requests, chapter ranges that would require discovery or scraping, third-party reader URLs, pages requiring a browser/session/access-token bypass, encrypted or DRM-protected downloads, source domains outside the allow-list, HTML or image-page responses, unknown binary types, and any request that does not include an explicit rights statement.

## Preflight protocol

| Stage | Required result | Failure behavior |
|---|---|---|
| Resolve title | Existing active record for the current chat | Ask administrator to track the title first. |
| Verify chapter | A bounded chapter identifier supplied by the requester | Ask for the exact chapter number or label. |
| Verify rights | Explicit user statement of authorization | Stop and explain that Lily needs rights confirmation. |
| Verify host | HTTPS direct URL whose host matches `LILY_ALLOWED_CHAPTER_DOMAINS` | Stop without making a request. |
| Verify gate | `LILY_ALLOW_DIRECT_CHAPTER_DOWNLOADS=true` | Report that host policy disables the capability. |
| Verify response | PDF, ZIP, or CBZ MIME type within size limit | Delete partial output and report a concise failure. |
| Confirm | Requester-owned unexpired approval | Do not enqueue before confirmation. |

The host-level allow-list must contain only sources the operator has independently approved. Lily never treats an LLM answer, public search result, user-supplied domain, or `Yes` callback as source approval.

## Delivery and posting

Once an approved file is complete, Lily sends it only to the originating chat. Posting to a channel is a separate action that verifies Lily’s and the requester’s Telegram permissions. An announcement must identify the information source and avoid fabricated availability, scan-quality, rating, review, or release claims. When a source is public-domain or creator-owned, the operator may add a plain provenance line in the draft.

## Example compliant request

```text
Lily, I have distribution rights for this creator-owned title.
Track manhua Example Studio Series at chapter 12.
Lily, download 12 Example Studio Series chapter https://downloads.example-studio.com/example-series-12.cbz
```

The production host must still contain `downloads.example-studio.com` in `LILY_ALLOWED_CHAPTER_DOMAINS`; the feature stays disabled until the host policy allows it.
