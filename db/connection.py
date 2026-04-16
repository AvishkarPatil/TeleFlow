from __future__ import annotations

from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from config import settings
from logging_config import get_logger

log = get_logger(__name__)

_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None


async def init_db() -> AsyncIOMotorDatabase:
    global _client, _db
    if _db is not None:
        return _db

    log.info("db.connecting")
    _client = AsyncIOMotorClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=10_000,
        connectTimeoutMS=10_000,
        socketTimeoutMS=30_000,
    )
    _db = _client[settings.mongodb_db_name]
    await _create_indexes(_db)
    log.info("db.connected", database=settings.mongodb_db_name)
    return _db


async def close_db() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
        _client = None
        _db = None
        log.info("db.disconnected")


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Database not initialised. Call init_db() at startup.")
    return _db


async def _create_indexes(db: AsyncIOMotorDatabase) -> None:
    await db["tasks"].create_index("task_id", unique=True)
    await db["tasks"].create_index("user_id")
    await db["tasks"].create_index("status")
    await db["tasks"].create_index("created_at")
    await db["users"].create_index("user_id", unique=True)
    await db["users"].create_index("is_sudo")
    await db["logs"].create_index("task_id")
    await db["logs"].create_index("user_id")
    await db["logs"].create_index("logged_at")
