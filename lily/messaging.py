from __future__ import annotations

from typing import Any

from .rich import heading, paragraph, rich


async def send_long_rich(chat_id: int, content: str, title: str = "Lily", reply_to: int | None = None, page_size: int = 3500) -> list[dict[str, Any]]:
    content = content or ""
    chunks = [content[index:index + page_size] for index in range(0, len(content), page_size)] or [""]
    sent = []
    for index, chunk in enumerate(chunks, start=1):
        page_title = title if len(chunks) == 1 else f"{title} · {index}/{len(chunks)}"
        sent.append(await rich.send(chat_id, [heading(page_title, 2), paragraph(chunk)], reply_to=reply_to if index == 1 else None))
    return sent
