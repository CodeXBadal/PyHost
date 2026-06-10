"""
Document helpers for every MongoDB collection.

These are not ORM classes — they're thin async helpers that wrap the
Motor collection so the rest of the code reads cleanly.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .connection import db


# ────────────────────────────────────────────────────────────
# users
# ────────────────────────────────────────────────────────────
async def get_or_create_user(user_id: int, username: str | None) -> Dict[str, Any]:
    user = await db.users.find_one({"user_id": user_id})
    now = datetime.now(timezone.utc)
    if user is None:
        user = {
            "user_id":         user_id,
            "username":        username or "",
            "plan":            "free",
            "is_banned":       False,
            "joined_at":       now,
            "projects_count":  0,
            "last_active":     now,
            "plan_expiry":     None,
        }
        await db.users.insert_one(user)
    else:
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"last_active": now, "username": username or user.get("username", "")}},
        )
    return user


async def update_user(user_id: int, fields: Dict[str, Any]) -> None:
    await db.users.update_one({"user_id": user_id}, {"$set": fields})


async def set_user_plan(user_id: int, plan: str, days: int = 30) -> None:
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"plan": plan, "plan_expiry": time.time() + days * 86400}},
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
        "project_id":         uuid.uuid4().hex[:12],
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
        "auto_restart":        True,
        "port":                None,
        "public_url":          None,
    }
    await db.projects.insert_one(project)
    await db.users.update_one({"user_id": user_id}, {"$inc": {"projects_count": 1}})
    return project


async def get_project(project_id: str) -> Optional[Dict[str, Any]]:
    return await db.projects.find_one({"project_id": project_id})


async def get_project_by_name(user_id: int, name: str) -> Optional[Dict[str, Any]]:
    return await db.projects.find_one({"user_id": user_id, "name": name})


async def update_project(project_id: str, fields: Dict[str, Any]) -> None:
    await db.projects.update_one({"project_id": project_id}, {"$set": fields})


async def delete_project(project_id: str) -> None:
    proj = await get_project(project_id)
    if proj:
        await db.users.update_one(
            {"user_id": proj["user_id"]}, {"$inc": {"projects_count": -1}}
        )
    await db.projects.delete_one({"project_id": project_id})
    await db.env_vars.delete_many({"project_id": project_id})
    await db.resource_logs.delete_many({"project_id": project_id})
    await db.crash_logs.delete_many({"project_id": project_id})
    await db.backups.delete_many({"project_id": project_id})
    await db.schedules.delete_many({"project_id": project_id})


async def list_projects(user_id: int) -> List[Dict[str, Any]]:
    return [p async for p in db.projects.find({"user_id": user_id}).sort("created_at", -1)]


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
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    cutoff_dt = datetime.fromtimestamp(cutoff, tz=timezone.utc)
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
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    cutoff_dt = datetime.fromtimestamp(cutoff, tz=timezone.utc)
    return [c async for c in db.crash_logs.find(
        {"project_id": project_id, "timestamp": {"$gte": cutoff_dt}}
    ).sort("timestamp", -1)]


async def all_recent_crashes(hours: int = 24) -> List[Dict[str, Any]]:
    cutoff = datetime.now(timezone.utc).timestamp() - hours * 3600
    cutoff_dt = datetime.fromtimestamp(cutoff, tz=timezone.utc)
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
