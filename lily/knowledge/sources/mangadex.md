# MangaDex Official API Notes

This note records externally verified constraints for Lily’s **metadata and release-tracking** integration. The API endpoint is `https://api.mangadex.org`. MangaDex requires TLS and a genuine `User-Agent` header. Its general documented allowance is approximately **5 requests per second per IP address**; persistent requests after `429` can lead to temporary `403` blocks or further cooldown. Lily therefore uses a conservative lower client-side rate, caching, a small page size, and stops/reports a source cooldown rather than retrying aggressively.[1]

MangaDex’s API documentation permits metadata endpoints for manga search, manga details, feeds, authors, groups, covers, and statistics. It explicitly says that clients **must credit MangaDex**, and that clients offering the ability to read chapters must also credit scanlation groups; it further forbids ads or paid services around apps that consume the API.[2]

Lily’s first integration scope is intentionally limited to title search, normalized title records, release-feed metadata, source identifiers, and announcement drafts with a MangaDex attribution. It does not call the MangaDex@Home endpoint, proxy reader images, open reader pages, mirror chapter files, download chapter content, or offer a chapter-reading service. Any future reader capability needs independent legal, policy, attribution, source-proxy, and licensing review.

## References

[1]: https://api.mangadex.org/docs/2-limitations/ "MangaDex API limitations and requirements"
[2]: https://api.mangadex.org/docs/swagger.html "MangaDex API Swagger and acceptable use policy"
