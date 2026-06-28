"""Motor async MongoDB connection + index bootstrap.

FIX for BUG-031: previously an empty MONGO_URI silently caused motor to
connect to localhost:27017, hiding the misconfiguration until the first
query timed out.  We now raise a clear error at import time when the
URI or database name is missing.  The check can be disabled in unit
tests by setting PYHOST_DB_SKIP_CHECK=1.
"""
from __future__ import annotations

import logging
import os

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from config import MONGO_URI, MONGO_DB_NAME

log = logging.getLogger(__name__)


def _check_config() -> None:
    if os.getenv("PYHOST_DB_SKIP_CHECK") == "1":
        return
    if not MONGO_URI:
        raise RuntimeError(
            "MONGO_URI is empty — set it in your .env file. "
            "Refusing to silently fall back to localhost:27017."
        )
    if not MONGO_DB_NAME:
        raise RuntimeError(
            "MONGO_DB_NAME is empty — set it in your .env file."
        )


_check_config()

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
