"""Motor async MongoDB connection + index bootstrap."""
from __future__ import annotations

import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from config import MONGO_URI, MONGO_DB_NAME

log = logging.getLogger(__name__)

_client: AsyncIOMotorClient = AsyncIOMotorClient(MONGO_URI, tz_aware=True)
db: AsyncIOMotorDatabase = _client[MONGO_DB_NAME]


async def init_indexes() -> None:
    """Create the indexes we rely on. Safe to call repeatedly."""
    try:
        await db.users.create_index("user_id", unique=True)
        await db.projects.create_index("project_id", unique=True)
        await db.projects.create_index([("user_id", 1), ("name", 1)])
        await db.env_vars.create_index([("project_id", 1), ("key", 1)], unique=True)
        await db.resource_logs.create_index([("project_id", 1), ("timestamp", -1)])
        await db.crash_logs.create_index([("project_id", 1), ("timestamp", -1)])
        await db.backups.create_index([("project_id", 1), ("created_at", -1)])
        await db.schedules.create_index("schedule_id", unique=True)
        log.info("MongoDB indexes ensured.")
    except Exception as exc:  # pragma: no cover
        log.exception("Failed to create indexes: %s", exc)


async def close_db() -> None:
    _client.close()
    log.info("MongoDB connection closed.")
