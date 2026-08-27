# Reference Capability Matrix

Lily treats every user-provided repository as reference material, not as a source for blind code import. It independently implements product behavior only when the feature fits Lily’s security model, Telegram policies, and service architecture.

| Repository | Declared license or status | Useful product concepts | Lily decision |
|---|---|---|---|
| Auto-Rename | Apache-2.0 | Safe filenames, caption-driven names, bulk workflow patterns | Continue independently implemented rename templates and add explicit batch-preview later. |
| FileToLink | No root license found | Expiring file links | Existing signed stream links; no source copying. |
| AniwatchTvdl | GPL-3.0 | Media search and title metadata concepts | Do not copy code; Lily uses lawful metadata/search patterns only. |
| ENCODING-BOT | AGPL-3.0 | Queue and FFmpeg job visibility | Existing independent queue and encoding tools; do not copy code. |
| LLM-Powered-Intelligent-Query-Retrieval-System | GPL-3.0 | Retrieval and query workflow concepts | Do not copy code; future retrieval remains an independent, opt-in feature. |
| Post-Search-Bot | MIT | Indexed channel-post search and pagination | Existing independent post index/search and owner-bound pagination. |
| Obra-ai | Architecture not adopted as source | AI-first conversational control | Existing independent natural-language planner and confirmation model. |
| awesome-free-llm-apis | CC0 catalog | Provider catalog and endpoint discovery | Existing curated profile catalog, privacy tiers, and ordered fallback. |
| awesome-llm-apps | Apache-2.0 | Agent workflow patterns | Existing independent plugin, plan, and tool-registry model. |
| bot-host | No root license found in clone | Isolated environments, dependency-change markers, project runner ideas | Existing independent managed registry, virtualenv isolation, and requirements hashing; no source copying. |
| Manhua-Bot | MIT | Series tracking, chapter status, queue visibility, rich announcement flow | Add a lawful manual series tracker and channel-post preparation; exclude adult sources, scraping, and copyright-infringing direct downloads. |

The next compatible Manhua-oriented capability is a **manual series release tracker**. An administrator can track a title, record a known chapter number, choose a target channel later, view tracked titles, and prepare an announcement. It does not scrape unsupported sources or download copyrighted chapter files.

## References

[1]: https://github.com/Beasgohan-code/Manhua-Bot "Manhua-Bot repository"
[2]: https://github.com/Beasgohan-code/bot-host/tree/main "bot-host repository"
