"""
Document helpers for every MongoDB collection.

These are not ORM classes — they're thin async helpers that wrap the
Motor collection so the rest of the code reads cleanly.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from pymongo import ReturnDocument

from .connection import db

log = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────
# users
# ────────────────────────────────────────────────────────────
async def get_or_create_user(user_id: int, username: str | None) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    # Atomic upsert — avoids the find_one + insert_one race where two
    # simultaneous /start commands could create duplicate user documents.
    # FIX: username sirf $set mein rakha, $setOnInsert se hataya - conflict avoid karne ke liye
    set_fields: Dict[str, Any] = {
        "last_active": now,
        "username": username or ""
    }

    user = await db.users.find_one_and_update(
        {"user_id": user_id},
        {
            "$setOnInsert": {
                "user_id":        user_id,
                "plan":           "free",
                "is_banned":      False,
                "joined_at":      now,
                "projects_count": 0,
                "plan_expiry":    None,
            },
            "$set": set_fields,
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return user


async def update_user(user_id: int, fields: Dict[str, Any]) -> None:
    await db.users.update_one({"user_id": user_id}, {"$set": fields})


async def set_user_plan(user_id: int, plan: str, days: int = 30) -> None:
    """Set a user's plan and its expiry timestamp.

    FIX for BUG-029: plan_expiry is now consistently a datetime (with UTC
    timezone) — previously it was a raw Unix float, which conflicted with
    the None / datetime values written elsewhere and caused TypeError on
    display / comparison.
    """
    expiry = datetime.now(timezone.utc) + timedelta(days=days)
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"plan": plan, "plan_expiry": expiry}},
        upsert=True,
    )


async def ban_user(user_id: int, banned: bool = True) -> None:
    await db.users.update_one({"user_id": user_id}, {"$set": {"is_banned": banned}})


async def all_users(skip: int = 0, limit: int = 20) -> List[Dict[str, Any]]:
    return [u async for u in db.users.find().sort("joined_at", -1).skip(skip).limit(limit)]


async def count_users() -> int:
    return await db.users.count_documents({})


# ────────────────────────────────────────────────────────────
# projects
# ────────────────────────────────────────────────────────────
async def create_project(user_id: int, name: str, python_version: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    project = {
        "project_id":         uuid.uuid4().hex,
        "user_id":             user_id,
        "name":                name,
        "container_id":        None,
        "python_version":      python_version,
        "run_command":         "python main.py",
        "status":              "created",          # created | running | stopped | crashed
        "created_at":          now,
        "last_started":        None,
        "last_error_at":       None,
        "crash_count_today":   0,
        "restart_count_today": 0,
        "auto_restart":        True,
        "port":                None,
        "public_url":          None,
    }
    await db.projects.insert_one(project)
    await db.users.update_one({"user_id": user_id}, {"$inc": {"projects_count": 1}})
    return project


async def get_project(project_id: str) -> Optional[Dict[str, Any]]:
    """
    FIX for OLD-DB-001: Primary lookup by project_id field.
    Falls back to ObjectId lookup if the string looks like a Mongo ObjectId
    (24 hex chars), for backward compatibility with very old records.
    """
    import re
    from bson import ObjectId
    from bson.errors import InvalidId

    # Normal case — 32-char hex project_id
    proj = await db.projects.find_one({"project_id": project_id})
    if proj:
        return proj

    # Legacy fallback — 24-char ObjectId string
    if re.match(r"^[0-9a-f]{24}$", project_id or ""):
        try:
            proj = await db.projects.find_one({"_id": ObjectId(project_id)})
        except InvalidId:
            pass
    return proj


async def get_project_by_name(user_id: int, name: str) -> Optional[Dict[str, Any]]:
    return await db.projects.find_one({"user_id": user_id, "name": name})


async def update_project(project_id: str, fields: Dict[str, Any]) -> None:
    await db.projects.update_one({"project_id": project_id}, {"$set": fields})


async def delete_project(project_id: str) -> None:
    """Delete a project and all of its child documents.

    FIX for BUG-032: every related collection is now wiped first, and the
    project document last.  Each delete is wrapped in try/except so a
    transient failure on one collection cannot leak the others — we log
    and keep going.  True multi-document atomicity needs a MongoDB replica
    set (transactions), which is out of scope; best-effort cleanup with
    explicit logging is the next-best guarantee.

    FIX for BUG-030: projects_count is decremented with a $max guard so it
    can never drop below zero on race / replay.
    """
    proj = await get_project(project_id)
    if not proj:
        return

    # Order: children first, parent last.  If we crash mid-way, a
    # subsequent retry can still find the project document and finish.
    for coll_name in ("env_vars", "resource_logs", "crash_logs",
                      "backups", "schedules"):
        try:
            await getattr(db, coll_name).delete_many({"project_id": project_id})
        except Exception as exc:
            log.exception("delete_project: failed to wipe %s for %s: %s",
                          coll_name, project_id, exc)

    try:
        await db.projects.delete_one({"project_id": project_id})
    except Exception as exc:
        log.exception("delete_project: failed to delete project %s: %s",
                      project_id, exc)
        return

    # BUG-030: clamp projects_count to >= 0.  We do it with a 2-step
    # operation: $inc then $max — Mongo's update operators can't combine
    # them in a single $set on the same field.
    try:
        await db.users.update_one(
            {"user_id": proj["user_id"]},
            {"$inc": {"projects_count": -1}},
        )
        await db.users.update_one(
            {"user_id": proj["user_id"], "projects_count": {"$lt": 0}},
            {"$set": {"projects_count": 0}},
        )
    except Exception as exc:
        log.exception("delete_project: failed to update user counter: %s", exc)


async def list_projects(user_id: int) -> List[Dict[str, Any]]:
    """
    FIX for OLD-DB-001: Old project records may be missing the 'project_id'
    field entirely, or stored under '_id' (ObjectId) from a legacy schema.

    This function:
    1. Fetches all projects for the user
    2. For any record missing a valid 32-char hex project_id, auto-migrates
       it in-place by assigning a new uuid hex and writing it to MongoDB.
    3. Returns only records that have (or now have) a valid project_id.

    This means old projects become clickable immediately without any manual
    DB migration script.
    """
    import re
    _HEX32 = re.compile(r"^[0-9a-f]{32}$")
    projects = []
    async for p in db.projects.find({"user_id": user_id}).sort("created_at", -1):
        pid = p.get("project_id", "")
        # If project_id is missing or not 32-char hex → migrate it now
        if not pid or not _HEX32.match(str(pid)):
            new_pid = uuid.uuid4().hex          # always valid 32-char hex
            try:
                await db.projects.update_one(
                    {"_id": p["_id"]},
                    {"$set": {"project_id": new_pid}},
                )
                p["project_id"] = new_pid
                log.info("list_projects: migrated old project _id=%s → project_id=%s",
                         p["_id"], new_pid)
            except Exception as exc:
                log.exception("list_projects: failed to migrate project _id=%s: %s",
                              p["_id"], exc)
                continue   # skip unmigratable record rather than crash
        # Ensure required display fields have safe defaults
        p.setdefault("name",   "Unnamed Project")
        p.setdefault("status", "unknown")
        projects.append(p)
    return projects


async def all_projects() -> List[Dict[str, Any]]:
    return [p async for p in db.projects.find()]


# ────────────────────────────────────────────────────────────
# env_vars
# ────────────────────────────────────────────────────────────
async def upsert_env(project_id: str, key: str, encrypted_value: str) -> None:
    await db.env_vars.update_one(
        {"project_id": project_id, "key": key},
        {"$set": {"value": encrypted_value,
                  "added_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


async def delete_env(project_id: str, key: str) -> None:
    await db.env_vars.delete_one({"project_id": project_id, "key": key})


async def list_envs(project_id: str) -> List[Dict[str, Any]]:
    return [e async for e in db.env_vars.find({"project_id": project_id}).sort("key", 1)]


# ────────────────────────────────────────────────────────────
# resource_logs
# ────────────────────────────────────────────────────────────
async def log_resources(project_id: str, ram_mb: float, cpu_pct: float,
                        requests_count: int = 0) -> None:
    await db.resource_logs.insert_one({
        "project_id":     project_id,
        "timestamp":      datetime.now(timezone.utc),
        "ram_mb":         ram_mb,
        "cpu_percent":    cpu_pct,
        "requests_count": requests_count,
    })


async def recent_resources(project_id: str, days: int = 7) -> List[Dict[str, Any]]:
    # BUG-034: simplified cutoff calculation using timedelta.
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days)
    return [r async for r in db.resource_logs.find(
        {"project_id": project_id, "timestamp": {"$gte": cutoff_dt}}
    ).sort("timestamp", 1)]


# ────────────────────────────────────────────────────────────
# crash_logs
# ────────────────────────────────────────────────────────────
async def log_crash(doc: Dict[str, Any]) -> None:
    doc.setdefault("timestamp", datetime.now(timezone.utc))
    await db.crash_logs.insert_one(doc)


async def recent_crashes(project_id: str, days: int = 7) -> List[Dict[str, Any]]:
    # BUG-034: simplified cutoff calculation using timedelta.
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days)
    return [c async for c in db.crash_logs.find(
        {"project_id": project_id, "timestamp": {"$gte": cutoff_dt}}
    ).sort("timestamp", -1)]


async def all_recent_crashes(hours: int = 24) -> List[Dict[str, Any]]:
    # BUG-034: simplified cutoff calculation using timedelta.
    cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=hours)
    return [c async for c in db.crash_logs.find(
        {"timestamp": {"$gte": cutoff_dt}}
    ).sort("timestamp", -1)]


# ────────────────────────────────────────────────────────────
# backups
# ────────────────────────────────────────────────────────────
async def add_backup(project_id: str, user_id: int, file_path: str, size_bytes: int) -> Dict[str, Any]:
    doc = {
        "backup_id":  uuid.uuid4().hex[:10],
        "project_id": project_id,
        "user_id":    user_id,
        "file_path":  file_path,
        "size_bytes": size_bytes,
        "created_at": datetime.now(timezone.utc),
    }
    await db.backups.insert_one(doc)
    return doc


async def list_backups(project_id: str) -> List[Dict[str, Any]]:
    return [b async for b in db.backups.find({"project_id": project_id}).sort("created_at", -1)]


async def delete_backup(backup_id: str) -> Optional[Dict[str, Any]]:
    doc = await db.backups.find_one({"backup_id": backup_id})
    if doc:
        await db.backups.delete_one({"backup_id": backup_id})
    return doc


# ────────────────────────────────────────────────────────────
# schedules
# ────────────────────────────────────────────────────────────
async def add_schedule(project_id: str, action: str, cron_expression: str) -> Dict[str, Any]:
    doc = {
        "schedule_id":     uuid.uuid4().hex[:10],
        "project_id":      project_id,
        "action":          action,
        "cron_expression": cron_expression,
        "last_run":        None,
        "next_run":        None,
        "is_active":       True,
    }
    await db.schedules.insert_one(doc)
    return doc


async def list_schedules(project_id: str) -> List[Dict[str, Any]]:
    return [s async for s in db.schedules.find({"project_id": project_id})]


async def delete_schedule(schedule_id: str) -> None:
    await db.schedules.delete_one({"schedule_id": schedule_id})
