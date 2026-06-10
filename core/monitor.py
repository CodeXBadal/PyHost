"""
Crash watcher + auto-restart for every running project.

A single asyncio Task that polls docker container statuses every few seconds.
When a project's container transitions running -> exited (or its inner
process dies — detected via the PID we wrote to /tmp/pyhost.pid), we:

  1. Pull the latest stats / logs and dispatch to error_logger.
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
from .docker_manager import docker_manager
from .error_logger import on_container_crashed

log = logging.getLogger(__name__)

# In-process state — survives until bot restart
_last_seen_status: Dict[str, str] = {}
_restart_attempts: Dict[str, int] = {}
_last_restart_at: Dict[str, float] = {}


async def _check_inner_process_alive(project_id: str) -> bool:
    """Check whether the project process inside the container is still up."""
    cmd = "test -f /tmp/pyhost.pid && kill -0 $(cat /tmp/pyhost.pid) 2>/dev/null && echo OK || echo DEAD"
    code, out = await docker_manager.exec_command(project_id, cmd)
    return "OK" in (out or "")


async def _attempt_auto_restart(bot: Bot, project_id: str) -> None:
    """Fire-and-forget restart logic, respecting cooldown & attempt cap."""
    attempts = _restart_attempts.get(project_id, 0)
    if attempts >= AUTO_RESTART_MAX_ATTEMPTS:
        log.info("Max auto-restart attempts reached for %s", project_id)
        return

    last = _last_restart_at.get(project_id, 0)
    if time.time() - last < AUTO_RESTART_COOLDOWN_SEC:
        return  # still in cooldown — wait

    proj = await get_project(project_id)
    if not proj or not proj.get("auto_restart"):
        return

    _restart_attempts[project_id] = attempts + 1
    _last_restart_at[project_id]  = time.time()

    # Decrypt env vars
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
    """One pass: check every project, dispatch crash callbacks."""
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

        stats = await docker_manager.get_stats(pid)
        # detect crash: container missing / exited / inner pid dead
        crashed = False
        exit_code = 1
        if stats["status"] in ("exited", "dead", "missing"):
            crashed = True
        else:
            alive = await _check_inner_process_alive(pid)
            if not alive:
                crashed = True

        if crashed:
            attempt = _restart_attempts.get(pid, 0) + 1
            try:
                await on_container_crashed(
                    bot=bot,
                    project_id=pid,
                    exit_code=exit_code,
                    restart_attempt=attempt,
                    uptime_seconds=stats.get("uptime_seconds", 0),
                    ram_mb=stats.get("ram_mb", 0),
                    cpu_pct=stats.get("cpu_percent", 0),
                )
            except Exception as exc:
                log.exception("on_container_crashed failed: %s", exc)
            await _attempt_auto_restart(bot, pid)
        else:
            # reset attempt counter once the container has been healthy for a while
            if stats.get("uptime_seconds", 0) > 120:
                _restart_attempts.pop(pid, None)


async def monitor_loop(bot: Bot, interval: int = 15) -> None:
    """Run forever — poll every `interval` seconds."""
    while True:
        try:
            await watcher_tick(bot)
        except Exception as exc:
            log.exception("monitor_loop tick failed: %s", exc)
        await asyncio.sleep(interval)
