"""
Crash watcher + auto-restart + resource alerts.

Fixes:
  - Memory leak fixed: state dicts cleaned up when project deleted/stopped
  - Resource alerts: notify user when RAM/CPU exceeds threshold
  - Cleaner state management with dataclass
  - asyncio.get_running_loop() instead of deprecated get_event_loop()
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict

from telegram import Bot

from config import (
    AUTO_RESTART_MAX_ATTEMPTS, AUTO_RESTART_COOLDOWN_SEC,
    RESOURCE_ALERT_RAM_PCT, RESOURCE_ALERT_CPU_PCT,
    RESOURCE_ALERT_COOLDOWN_SEC, PLAN_LIMITS,
)
from database.models import (
    all_projects, get_project, list_envs, update_project, get_or_create_user,
)
from .crypto import decrypt
from .process_manager import process_manager
from .error_logger import on_container_crashed

log = logging.getLogger(__name__)


@dataclass
class _ProjectState:
    restart_attempts: int = 0
    last_restart_at: float = 0.0
    last_alert_at: float = 0.0
    last_seen_status: str = ""


# Per-project watcher state — cleaned up when project not in DB
_state: Dict[str, _ProjectState] = {}


def _get_state(project_id: str) -> _ProjectState:
    if project_id not in _state:
        _state[project_id] = _ProjectState()
    return _state[project_id]


def _cleanup_stale_state(active_ids: set) -> None:
    """Remove state for projects that no longer exist — prevents memory leak."""
    stale = [pid for pid in _state if pid not in active_ids]
    for pid in stale:
        del _state[pid]
    if stale:
        log.debug("monitor: cleaned up state for %d removed projects", len(stale))


async def _attempt_auto_restart(bot: Bot, project_id: str) -> None:
    st = _get_state(project_id)
    if st.restart_attempts >= AUTO_RESTART_MAX_ATTEMPTS:
        return
    if time.time() - st.last_restart_at < AUTO_RESTART_COOLDOWN_SEC:
        return

    proj = await get_project(project_id)
    if not proj or not proj.get("auto_restart"):
        return

    st.restart_attempts += 1
    st.last_restart_at = time.time()

    envs = {e["key"]: decrypt(e["value"]) for e in await list_envs(project_id)}
    ok, err = await process_manager.restart_container(
        project_id, proj["run_command"], envs,
    )
    if ok:
        await update_project(project_id, {"status": "running"})
        log.info("Auto-restarted %s (attempt %d/%d)",
                 project_id, st.restart_attempts, AUTO_RESTART_MAX_ATTEMPTS)
    else:
        log.warning("Auto-restart failed for %s: %s", project_id, err)


async def _check_resource_alert(bot: Bot, project_id: str,
                                  stats: dict, proj: dict) -> None:
    """Send alert to user if RAM or CPU exceeds threshold."""
    st = _get_state(project_id)
    now = time.time()

    # Cooldown check — don't spam alerts
    if now - st.last_alert_at < RESOURCE_ALERT_COOLDOWN_SEC:
        return

    user = await get_or_create_user(proj["user_id"], None)
    limits = PLAN_LIMITS.get(user.get("plan", "free"), PLAN_LIMITS["free"])

    ram_pct = (stats["ram_mb"] / limits["ram_mb"] * 100) if limits["ram_mb"] else 0
    cpu_pct = stats["cpu_percent"]

    alert_parts = []
    if ram_pct >= RESOURCE_ALERT_RAM_PCT:
        alert_parts.append(
            f"💾 *RAM:* {stats['ram_mb']:.0f} MB / {limits['ram_mb']:.0f} MB "
            f"(*{ram_pct:.0f}%*)"
        )
    if cpu_pct >= RESOURCE_ALERT_CPU_PCT:
        alert_parts.append(f"⚡ *CPU:* {cpu_pct:.0f}%")

    if not alert_parts:
        return

    st.last_alert_at = now
    alert_text = (
        f"⚠️ *Resource Alert — {proj['name']}*\n\n"
        + "\n".join(alert_parts)
        + "\n\n_Consider restarting or upgrading your plan._"
    )
    try:
        from telegram.constants import ParseMode
        await bot.send_message(
            chat_id=proj["user_id"],
            text=alert_text,
            parse_mode=ParseMode.MARKDOWN,
        )
        log.info("Resource alert sent for project %s (RAM=%.0f%%, CPU=%.0f%%)",
                 project_id, ram_pct, cpu_pct)
    except Exception as exc:
        log.debug("Failed to send resource alert for %s: %s", project_id, exc)


async def watcher_tick(bot: Bot) -> None:
    try:
        projects = await all_projects()
    except Exception as exc:
        log.exception("watcher: failed to list projects: %s", exc)
        return

    active_ids = {p["project_id"] for p in projects}
    _cleanup_stale_state(active_ids)

    for p in projects:
        pid = p["project_id"]
        st = _get_state(pid)

        if p.get("status") != "running":
            # Reset restart counter when user manually stops
            st.restart_attempts = 0
            st.last_seen_status = p.get("status", "")
            continue

        alive = process_manager.is_project_alive(pid)

        if not alive:
            attempt = st.restart_attempts + 1
            stats = await process_manager.get_stats(pid)
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
            stats = await process_manager.get_stats(pid)
            # Reset restart counter after 2 min of stable uptime
            if stats.get("uptime_seconds", 0) > 120:
                st.restart_attempts = 0
            # Check resource thresholds
            await _check_resource_alert(bot, pid, stats, p)


async def monitor_loop(bot: Bot, interval: int = 15) -> None:
    while True:
        try:
            await watcher_tick(bot)
        except Exception as exc:
            log.exception("monitor_loop tick failed: %s", exc)
        await asyncio.sleep(interval)
