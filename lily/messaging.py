from __future__ import annotations

from typing import Any

from .rich import heading, paragraph, rich


def split_for_telegram(content: str, page_size: int = 3500) -> list[str]:
    """Split below the 4,096-character Bot API text limit at readable boundaries."""
    value = content or ""
    if not value:
        return [""]
    chunks: list[str] = []
    remaining = value
    while len(remaining) > page_size:
        window = remaining[:page_size + 1]
        cut = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(". "), window.rfind(" "))
        if cut < max(1, page_size // 2):
            cut = page_size
        else:
            cut += 1
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].lstrip()
    chunks.append(remaining)
    return chunks


async def send_long_rich(chat_id: int, content: str, title: str = "Lily", reply_to: int | None = None, page_size: int = 3500, *, compact: bool | None = None) -> list[dict[str, Any]]:
    from .config import settings
    compact = settings.compact_responses if compact is None else compact
    content = content or ""
    chunks = split_for_telegram(content, page_size)
    sent = []
    for index, chunk in enumerate(chunks, start=1):
        if compact:
            blocks = [paragraph(chunk)]
        else:
            page_title = title if len(chunks) == 1 else f"{title} · {index}/{len(chunks)}"
            blocks = [heading(page_title, 2), paragraph(chunk)]
        sent.append(await rich.send(chat_id, blocks, reply_to=reply_to if index == 1 else None))
    return sent
