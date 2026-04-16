from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from db.connection import get_db
from db.models import UserDocument, UserPrefs
from config import settings
from logging_config import get_logger

log = get_logger(__name__)


async def seed_sudo_users() -> None:
    for uid in settings.sudo_user_ids:
        existing = await get_db()["users"].find_one({"user_id": uid})
        if existing is None:
            doc = UserDocument(user_id=uid, first_name="(bootstrap)", is_sudo=True)
            await get_db()["users"].insert_one(doc.to_dict())
            log.info("user.sudo_seeded", user_id=uid)
        elif not existing.get("is_sudo"):
            await get_db()["users"].update_one({"user_id": uid}, {"$set": {"is_sudo": True}})
            log.info("user.sudo_elevated", user_id=uid)


async def is_sudo_user(user_id: int) -> bool:
    doc = await get_db()["users"].find_one(
        {"user_id": user_id, "is_sudo": True, "is_blocked": {"$ne": True}}
    )
    return doc is not None


async def get_user(user_id: int) -> Optional[UserDocument]:
    doc = await get_db()["users"].find_one({"user_id": user_id})
    return UserDocument.from_dict(doc) if doc else None


async def get_prefs(user_id: int) -> UserPrefs:
    user = await get_user(user_id)
    return user.prefs if user else UserPrefs()


async def update_prefs(user_id: int, **fields) -> None:
    update = {f"prefs.{k}": v for k, v in fields.items()}
    await get_db()["users"].update_one({"user_id": user_id}, {"$set": update})


async def upsert_user(user_id: int, username: str | None, first_name: str) -> None:
    await get_db()["users"].update_one(
        {"user_id": user_id},
        {
            "$set": {"username": username, "first_name": first_name},
            "$setOnInsert": {
                "user_id": user_id,
                "is_sudo": False,
                "is_blocked": False,
                "added_at": datetime.utcnow(),
                "total_tasks": 0,
                "total_bytes_transferred": 0,
                "prefs": UserPrefs().to_dict(),
            },
        },
        upsert=True,
    )


async def add_sudo(user_id: int, granted_by: int, username: str | None = None) -> bool:
    existing = await get_db()["users"].find_one({"user_id": user_id})
    if existing and existing.get("is_sudo"):
        return False
    await get_db()["users"].update_one(
        {"user_id": user_id},
        {
            "$set": {
                "is_sudo": True,
                "added_by": granted_by,
                "added_at": datetime.utcnow(),
                "username": username,
            },
            "$setOnInsert": {
                "user_id": user_id,
                "first_name": "",
                "is_blocked": False,
                "total_tasks": 0,
                "total_bytes_transferred": 0,
                "prefs": UserPrefs().to_dict(),
            },
        },
        upsert=True,
    )
    log.info("user.sudo_granted", user_id=user_id, granted_by=granted_by)
    return True


async def remove_sudo(user_id: int) -> bool:
    result = await get_db()["users"].update_one(
        {"user_id": user_id, "is_sudo": True},
        {"$set": {"is_sudo": False}},
    )
    if result.modified_count:
        log.info("user.sudo_revoked", user_id=user_id)
        return True
    return False


async def list_sudo_users() -> List[UserDocument]:
    cursor = get_db()["users"].find({"is_sudo": True}).sort("added_at", 1)
    return [UserDocument.from_dict(doc) async for doc in cursor]


async def increment_task_stats(user_id: int, bytes_transferred: int) -> None:
    await get_db()["users"].update_one(
        {"user_id": user_id},
        {"$inc": {"total_tasks": 1, "total_bytes_transferred": bytes_transferred}},
    )
