from __future__ import annotations

from db.connection import get_db
from db.models import TransferLogDocument
from logging_config import get_logger

log = get_logger(__name__)


async def log_transfer(entry: TransferLogDocument) -> None:
    try:
        await get_db()["logs"].insert_one(entry.to_dict())
    except Exception as e:
        log.error("transfer_log.write_failed", error=str(e))


async def get_user_stats(user_id: int) -> dict:
    pipeline = [
        {"$match": {"user_id": user_id, "success": True}},
        {"$group": {
            "_id": None,
            "total_transfers": {"$sum": 1},
            "total_bytes": {"$sum": "$file_size"},
            "avg_speed_bps": {"$avg": "$avg_speed_bps"},
        }},
    ]
    async for doc in get_db()["logs"].aggregate(pipeline):
        return {
            "total_transfers": doc.get("total_transfers", 0),
            "total_bytes": doc.get("total_bytes", 0),
            "avg_speed_bps": doc.get("avg_speed_bps", 0.0),
        }
    return {"total_transfers": 0, "total_bytes": 0, "avg_speed_bps": 0.0}
