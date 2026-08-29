"""Advisor–orchestrator–worker research pattern for Lily."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from .web_media import WebSearch


SearchFn = Callable[[str, int], Awaitable[list[dict[str, Any]]]]


class ResearchOrchestrator:
    """Run bounded parallel scouts and synthesize a cited summary."""

    def __init__(self, search: WebSearch | None = None) -> None:
        self._search = search or WebSearch()

    async def _safe_search(self, angle: str, results_per_scout: int) -> list[dict[str, Any]]:
        try:
            return await self._search.search(angle, limit=results_per_scout)
        except Exception:
            return []

    async def run(self, query: str, *, scouts: int = 3, results_per_scout: int = 3) -> dict[str, Any]:
        query = str(query or "").strip()[:500]
        if not query:
            return {"query": "", "waves": [], "sources": [], "summary": "Provide a research question."}
        scouts = max(1, min(int(scouts), 4))
        angles = _scout_angles(query, scouts)
        # Run the scout angles concurrently: they are independent reads, so
        # mission latency becomes the slowest scout instead of the sum of all.
        batches = await asyncio.gather(*(self._safe_search(angle, results_per_scout) for angle in angles))
        waves: list[dict[str, Any]] = []
        all_results: list[dict[str, Any]] = []
        for index, batch in enumerate(batches, start=1):
            angle = angles[index - 1]
            waves.append({"wave": index, "angle": angle, "result_count": len(batch)})
            for item in batch:
                link = str(item.get("link") or item.get("url") or "")
                title = str(item.get("title") or "Untitled")[:200]
                snippet = str(item.get("snippet") or item.get("body") or "")[:400]
                if link and not any(existing.get("link") == link for existing in all_results):
                    all_results.append({"title": title, "link": link, "snippet": snippet, "wave": index})
        summary = _synthesize(query, all_results)
        return {
            "query": query,
            "waves": waves,
            "sources": all_results[:12],
            "summary": summary,
            "scout_count": scouts,
        }


def _scout_angles(query: str, count: int) -> list[str]:
  base = query.strip()
  variants = [
      base,
      f"{base} overview",
      f"{base} latest",
      f"{base} best practices",
  ]
  return variants[:count]


def _synthesize(query: str, sources: list[dict[str, Any]]) -> str:
    if not sources:
        return f"No web results were returned for “{query}”. Check LILY_WEB_SEARCH_URL or try a narrower question."
    lines = [f"**Research summary for:** {query}", ""]
    for index, item in enumerate(sources[:8], start=1):
        lines.append(f"{index}. [{item['title']}]({item['link']})")
        if item.get("snippet"):
            lines.append(f"   {item['snippet'][:280]}")
    if len(sources) > 8:
        lines.append(f"\n_+ {len(sources) - 8} more source(s) omitted for length._")
    return "\n".join(lines)[:3_800]


async def parallel_research(query: str, scouts: int = 3) -> dict[str, Any]:
    orchestrator = ResearchOrchestrator()
    return await orchestrator.run(query, scouts=scouts)
