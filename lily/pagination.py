from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .rich import heading, inline_keyboard, paragraph, table


@dataclass
class SearchSession:
    token: str
    owner_id: int
    chat_id: int
    query: str
    results: list[dict[str, Any]]
    page_size: int = 5
    page: int = 0
    created_at: float = 0.0

    @property
    def pages(self) -> int:
        return max(1, (len(self.results) + self.page_size - 1) // self.page_size)

    def current(self) -> list[dict[str, Any]]:
        start = self.page * self.page_size
        return self.results[start:start + self.page_size]


class PaginationManager:
    def __init__(self, ttl_seconds: int = 900):
        self.ttl_seconds = ttl_seconds
        self.sessions: dict[str, SearchSession] = {}

    def create(self, owner_id: int, chat_id: int, query: str, results: list[dict[str, Any]], page_size: int = 5) -> SearchSession:
        token = uuid.uuid4().hex[:12]
        session = SearchSession(token, owner_id, chat_id, query, results, max(1, min(page_size, 10)), 0, time.time())
        self.sessions[token] = session
        self.cleanup()
        return session

    def get(self, token: str) -> SearchSession | None:
        self.cleanup()
        return self.sessions.get(token)

    def cleanup(self) -> None:
        cutoff = time.time() - self.ttl_seconds
        self.sessions = {token: session for token, session in self.sessions.items() if session.created_at >= cutoff}

    def keyboard(self, session: SearchSession) -> dict[str, Any]:
        rows = []
        nav = []
        if session.page > 0:
            nav.append(("‹ Previous", f"search:{session.token}:prev"))
        if session.page < session.pages - 1:
            nav.append(("Next ›", f"search:{session.token}:next"))
        if nav:
            rows.append(nav)
        rows.append([("Refresh", f"search:{session.token}:refresh"), ("Close", f"search:{session.token}:close")])
        return inline_keyboard(rows)

    def blocks(self, session: SearchSession) -> list[dict[str, Any]]:
        rows = [["#", "Title", "Link"]]
        for index, item in enumerate(session.current(), start=session.page * session.page_size + 1):
            rows.append([str(index), str(item.get("title", "Untitled"))[:80], str(item.get("link") or f"message {item.get('message_id', '')}")[:100]])
        return [
            heading("Media search results", 2),
            paragraph(f"Search: {session.query}  ·  Page {session.page + 1}/{session.pages}  ·  {len(session.results)} result(s)"),
            table(rows, caption="Select a page to browse the indexed media posts."),
        ]


pagination = PaginationManager()
