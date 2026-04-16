from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

from core.link_parser import ParsedLink
from db import tasks as task_db
from db.models import TaskDocument, TaskStatus
from config import settings
from logging_config import get_logger

if TYPE_CHECKING:
    from pyrogram import Client

log = get_logger(__name__)


@dataclass
class TransferJob:
    task: TaskDocument
    reply_to_msg_id: int
    cancelled: bool = False


class TaskQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[TransferJob] = asyncio.Queue()
        self._workers: List[asyncio.Task] = []
        self._bot: Optional["Client"] = None
        self._user_acc: Optional["Client"] = None
        self._shutdown_event = asyncio.Event()

    async def start(self, bot: "Client", user_acc: Optional["Client"]) -> None:
        self._bot = bot
        self._user_acc = user_acc
        for i in range(settings.max_workers):
            worker = asyncio.create_task(self._worker_loop(i), name=f"worker-{i}")
            self._workers.append(worker)
        log.info("task_queue.started", workers=settings.max_workers)

    async def stop(self, drain_timeout: float = 120.0) -> None:
        log.info("task_queue.stopping", queue_depth=self._queue.qsize())
        self._shutdown_event.set()
        try:
            await asyncio.wait_for(self._queue.join(), timeout=drain_timeout)
        except asyncio.TimeoutError:
            log.warning("task_queue.drain_timeout", remaining=self._queue.qsize())
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        log.info("task_queue.stopped")

    async def enqueue(
        self,
        parsed: ParsedLink,
        user_id: int,
        dest_chat_id: int,
        user_chat_id: int,
        reply_to_msg_id: int,
    ) -> List[str]:
        active = await task_db.count_active_tasks_for_user(user_id)
        if active >= settings.max_tasks_per_user:
            raise RuntimeError(
                f"Too many active tasks. You have {active} running; "
                f"limit is {settings.max_tasks_per_user}."
            )

        task = TaskDocument(
            task_id=uuid.uuid4().hex[:8].upper(),
            user_id=user_id,
            status=TaskStatus.QUEUED,
            source_chat=parsed.source_chat,
            source_type=parsed.source_type,
            msg_id_start=parsed.msg_id_start,
            msg_id_end=parsed.msg_id_end,
            status_chat_id=dest_chat_id,
            user_chat_id=user_chat_id,
            created_at=datetime.utcnow(),
        )
        await task_db.create_task(task)
        await self._queue.put(TransferJob(task=task, reply_to_msg_id=reply_to_msg_id))

        log.info(
            "task_queue.enqueued",
            task_id=task.task_id,
            user_id=user_id,
            source=parsed.source_chat,
            range=f"{parsed.msg_id_start}-{parsed.msg_id_end}",
            count=parsed.message_count,
            queue_depth=self._queue.qsize(),
        )
        return [task.task_id]

    async def cancel_task(self, task_id: str, user_id: int) -> bool:
        task = await task_db.get_task(task_id)
        if task is None or task.user_id != user_id:
            return False
        if task.status in (TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.INTERRUPTED):
            return False
        await task_db.set_task_status(task_id, TaskStatus.CANCELLED)
        # Clean up any temp files for this task
        from utils.temp import cleanup_stale_files
        cleanup_stale_files(task_id)
        log.info("task.cancelled", task_id=task_id, by_user=user_id)
        return True

    def queue_depth(self) -> int:
        return self._queue.qsize()

    def worker_count(self) -> int:
        return len([w for w in self._workers if not w.done()])

    async def _worker_loop(self, worker_id: int) -> None:
        log.debug("worker.started", worker_id=worker_id)
        while not self._shutdown_event.is_set():
            try:
                job = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            try:
                await self._process_job(job, worker_id)
            except Exception:
                log.exception("worker.unhandled_error", worker_id=worker_id, task_id=job.task.task_id)
            finally:
                self._queue.task_done()
        log.debug("worker.stopped", worker_id=worker_id)

    async def _process_job(self, job: TransferJob, worker_id: int) -> None:
        task = job.task
        latest = await task_db.get_task(task.task_id)
        if latest is None or latest.status == TaskStatus.CANCELLED:
            log.info("worker.job_skipped_cancelled", task_id=task.task_id)
            return
        log.info(
            "worker.job_started",
            worker_id=worker_id,
            task_id=task.task_id,
            source=f"{task.source_chat}/{task.msg_id_start}",
        )
        from core.transfer_engine import execute
        await execute(task=latest, bot=self._bot, user_acc=self._user_acc, reply_to_msg_id=job.reply_to_msg_id)


queue = TaskQueue()
