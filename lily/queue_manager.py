from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .config import settings
from .db import Database, db


@dataclass
class QueueItem:
    job_id: str
    update: Any
    context: Any
    plan: Any
    executor: Callable[..., Awaitable[str]]


class EncodingQueue:
    def __init__(self, database: Database, workers: int = 1):
        self.db = database
        self.worker_count = max(1, workers)
        self.queue: asyncio.Queue[QueueItem] = asyncio.Queue()
        self.worker_tasks: list[asyncio.Task] = []
        self.running_tasks: dict[str, asyncio.Task] = {}
        self.started = False

    async def start(self) -> None:
        if self.started:
            return
        self.started = True
        for index in range(self.worker_count):
            self.worker_tasks.append(asyncio.create_task(self._worker(), name=f"lily-encoder-{index + 1}"))

    async def stop(self) -> None:
        for task in self.worker_tasks:
            task.cancel()
        if self.worker_tasks:
            await asyncio.gather(*self.worker_tasks, return_exceptions=True)
        self.worker_tasks.clear()
        self.started = False

    async def enqueue(self, update: Any, context: Any, plan: Any, executor: Callable[..., Awaitable[str]]) -> str:
        await self.start()
        job_id = uuid.uuid4().hex[:12]
        await self.db.create_encoding_job(job_id, update.effective_chat.id, update.effective_user.id, {"plan": plan.__dict__ if hasattr(plan, "__dict__") else plan})
        await self.queue.put(QueueItem(job_id, update, context, plan, executor))
        return job_id

    async def _worker(self) -> None:
        while True:
            item = await self.queue.get()
            record = await self.db.get_encoding_job(item.job_id)
            if record and record["state"] == "cancelled":
                self.running_tasks.pop(item.job_id, None)
                self.queue.task_done()
                continue
            task = asyncio.create_task(item.executor(item.update, item.context, item.plan), name=f"lily-job-{item.job_id}")
            self.running_tasks[item.job_id] = task
            await self.db.update_encoding_job(item.job_id, state="running", progress="Starting encoding…")
            try:
                item.context.user_data["_encoding_job_id"] = item.job_id
                await task
                await self.db.update_encoding_job(item.job_id, state="completed", progress="Completed")
            except asyncio.CancelledError:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                await self.db.update_encoding_job(item.job_id, state="cancelled", progress="Cancelled")
            except Exception as exc:
                await self.db.update_encoding_job(item.job_id, state="failed", error=str(exc), progress="Failed")
            finally:
                item.context.user_data.pop("_encoding_job_id", None)
                self.running_tasks.pop(item.job_id, None)
                self.queue.task_done()

    async def cancel(self, job_id: str, requester_id: int) -> tuple[bool, str]:
        item = await self.db.get_encoding_job(job_id)
        if not item:
            return False, "Encoding job not found."
        if item["user_id"] != requester_id:
            return False, "Only the user who started this encoding can cancel it."
        if item["state"] in {"completed", "failed", "cancelled"}:
            return False, f"This job is already {item['state']}."
        await self.db.update_encoding_job(job_id, state="cancelled", progress="Cancellation requested")
        task = self.running_tasks.get(job_id)
        if task and task is not asyncio.current_task():
            task.cancel()
        return True, "Cancellation requested."

    async def status(self, job_id: str, requester_id: int) -> dict[str, Any] | None:
        item = await self.db.get_encoding_job(job_id)
        if item and item["user_id"] != requester_id:
            return None
        return item

    async def list(self, chat_id: int, requester_id: int | None = None) -> list[dict[str, Any]]:
        items = await self.db.list_encoding_jobs(chat_id)
        if requester_id is None:
            return items
        return [item for item in items if item["user_id"] == requester_id]


encoding_queue = EncodingQueue(db, workers=settings.max_concurrent_jobs)
