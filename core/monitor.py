"""
Crash watcher + auto-restart for every running project.

Polls project process statuses every few seconds using ProcessManager.
When a project's process dies, we:
  1. Pull logs and dispatch to error_logger.
  2. Attempt auto-restart, up to AUTO_RESTART_MAX_ATTEMPTS with cooldown.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict

from telegram import Bot

from config import AUTO_RESTART_MAX_ATTEMPTS, AUTO_RESTART_COOLDOWN_SEC
from database.models import (
    all_projects, get_project, list_envs, update_project,
)
from .crypto import decrypt
from .process_manager import process_manager as docker_manager
from .error_logger import on_container_crashed

log = logging.getLogger(__name__)

_last_seen_status: Dict[str, str] = {}
_restart_attempts: Dict[str, int] = {}
_last_restart_at:  Dict[str, float] = {}


async def _attempt_auto_restart(bot: Bot, project_id: str) -> None:
    attempts = _restart_attempts.get(project_id, 0)
    if attempts >= AUTO_RESTART_MAX_ATTEMPTS:
        return

    last = _last_restart_at.get(project_id, 0)
    if time.time() - last < AUTO_RESTART_COOLDOWN_SEC:
        return

    proj = await get_project(project_id)
    if not proj or not proj.get("auto_restart"):
        return

    _restart_attempts[project_id] = attempts + 1
    _last_restart_at[project_id]  = time.time()

    envs = {}
    for e in await list_envs(project_id):
        envs[e["key"]] = decrypt(e["value"])

    ok, err = await docker_manager.restart_container(
        project_id, proj["run_command"], envs,
    )
    if ok:
        await update_project(project_id, {"status": "running"})
        log.info("Auto-restarted %s (attempt %d/%d)",
                 project_id, attempts + 1, AUTO_RESTART_MAX_ATTEMPTS)
    else:
        log.warning("Auto-restart failed for %s: %s", project_id, err)


async def watcher_tick(bot: Bot) -> None:
    try:
        projects = await all_projects()
    except Exception as exc:
        log.exception("watcher: failed to list projects: %s", exc)
        return

    for p in projects:
        pid = p["project_id"]
        if p.get("status") != "running":
            _restart_attempts.pop(pid, None)
            _last_seen_status[pid] = p.get("status", "")
            continue

        # Check if the process is actually alive
        alive = docker_manager.is_project_alive(pid)

        if not alive:
            stats = await docker_manager.get_stats(pid)
            attempt = _restart_attempts.get(pid, 0) + 1
            try:
                await on_container_crashed(
                    bot=bot,
                    project_id=pid,
                    exit_code=1,
                    restart_attempt=attempt,
                    uptime_seconds=stats.get("uptime_seconds", 0),
                    ram_mb=stats.get("ram_mb", 0),
                    cpu_pct=stats.get("cpu_percent", 0),
                )
            except Exception as exc:
                log.exception("on_container_crashed failed: %s", exc)
            await _attempt_auto_restart(bot, pid)
        else:
            stats = await docker_manager.get_stats(pid)
            if stats.get("uptime_seconds", 0) > 120:
                _restart_attempts.pop(pid, None)


async def monitor_loop(bot: Bot, interval: int = 15) -> None:
    while True:
        try:
            await watcher_tick(bot)
        except Exception as exc:
            log.exception("monitor_loop tick failed: %s", exc)
        await asyncio.sleep(interval)
