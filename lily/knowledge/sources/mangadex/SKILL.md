# MangaDex Metadata and Release Feed Skill

> This skill is a **metadata and release-feed** integration only. It does not turn Lily into a MangaDex chapter reader, page proxy, image fetcher, scraper, or bulk-download system.

Lily can search public MangaDex title metadata and inspect the recent release-feed metadata for a supplied MangaDex title ID. It uses the official `api.mangadex.org` interface and must present MangaDex as the source. It may include chapter number, chapter title, language, and published scanlation-group metadata as a release notice. It must not display pages, reproduce chapters, resolve MangaDex@Home locations, or transfer files from any reader or image endpoint.

## Host configuration and API pacing

The integration starts disabled. An operator must set `LILY_ENABLE_MANGADEX_METADATA=true` and a truthful `LILY_MANGADEX_USER_AGENT`. Lily refuses calls without both. The client limits itself to a conservative interval, caches identical metadata requests, and stops after an HTTP 429 rather than retrying aggressively. MangaDex documents a general allowance of approximately 5 requests per second per IP and warns that persistent calls after 429 can cause temporary blocks.[1]

| Setting | Purpose | Safe initial value |
|---|---|---|
| `LILY_ENABLE_MANGADEX_METADATA` | Enables only search and feed metadata endpoints | `false` |
| `LILY_MANGADEX_USER_AGENT` | Truthful client identifier with operator contact | `Lily/1.0 (operator@example.com)` |
| `LILY_MANGADEX_MIN_INTERVAL_SECONDS` | Minimum delay between upstream requests | `0.30` |
| `LILY_MANGADEX_CACHE_SECONDS` | In-memory identical-request cache interval | `300` |

## User workflows

```text
Lily, MangaDex search for Frieren.
Lily, show MangaDex recent chapters for 12345678-1234-1234-1234-123456789abc.
```

Lily returns a rich table with concise source attribution. An administrator can manually copy verified title facts into Lily’s existing tracked-series record and then prepare a source-attributed channel announcement. Lily must not claim a chapter is legally available, link to pages, create a download job, or infer that the user has a distribution right merely because metadata exists in a feed.

## MangaPill boundary

MangaPill does not currently have a verified official public API or documented authorization for Lily to scrape reader pages. Lily therefore supports only **manual approved links** for MangaPill. It will not search, scrape, resolve, proxy, or download chapter content from that service. A future integration needs written source authorization and a reviewed public API or publisher agreement before any automated feature is enabled.

## References

[1]: https://api.mangadex.org/docs/2-limitations/ "MangaDex API limitations and requirements"
[2]: https://api.mangadex.org/docs/swagger.html "MangaDex API acceptable use policy and endpoints"
