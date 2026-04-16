from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from db.connection import get_db
from db.models import TaskDocument, TaskStatus
from logging_config import get_logger

log = get_logger(__name__)


async def create_task(task: TaskDocument) -> TaskDocument:
    if not task.task_id:
        task.task_id = uuid.uuid4().hex[:8].upper()
    await get_db()["tasks"].insert_one(task.to_dict())
    return task


async def get_task(task_id: str) -> Optional[TaskDocument]:
    doc = await get_db()["tasks"].find_one({"task_id": task_id})
    return TaskDocument.from_dict(doc) if doc else None


async def update_task(task_id: str, **fields) -> None:
    await get_db()["tasks"].update_one({"task_id": task_id}, {"$set": fields})


async def set_task_status(
    task_id: str,
    status: str,
    *,
    error: str | None = None,
    msg_id_current: int | None = None,
) -> None:
    update: dict = {"status": status}
    if status == TaskStatus.RUNNING:
        update["started_at"] = datetime.utcnow()
    elif status in (TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.INTERRUPTED):
        update["completed_at"] = datetime.utcnow()
    if error is not None:
        update["error"] = error
    if msg_id_current is not None:
        update["msg_id_current"] = msg_id_current
    await update_task(task_id, **update)


async def count_active_tasks_for_user(user_id: int) -> int:
    return await get_db()["tasks"].count_documents(
        {"user_id": user_id, "status": {"$in": [TaskStatus.QUEUED, TaskStatus.RUNNING]}}
    )


async def get_recent_tasks(user_id: int, limit: int = 10) -> List[TaskDocument]:
    cursor = get_db()["tasks"].find({"user_id": user_id}).sort("created_at", -1).limit(limit)
    return [TaskDocument.from_dict(doc) async for doc in cursor]


async def get_all_active_tasks() -> List[TaskDocument]:
    cursor = get_db()["tasks"].find({"status": {"$in": [TaskStatus.QUEUED, TaskStatus.RUNNING]}})
    return [TaskDocument.from_dict(doc) async for doc in cursor]


async def mark_all_running_as_interrupted() -> int:
    result = await get_db()["tasks"].update_many(
        {"status": {"$in": [TaskStatus.RUNNING, TaskStatus.QUEUED]}},
        {"$set": {
            "status": TaskStatus.INTERRUPTED,
            "completed_at": datetime.utcnow(),
            "error": "Bot restarted while task was running.",
        }},
    )
    count = result.modified_count
    if count:
        log.warning("task.interrupted_on_startup", count=count)
    return count
