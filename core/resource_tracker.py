"""
APScheduler-driven RAM/CPU/uptime polling for every running project.

Fixes:
  - psutil calls run in thread executor (non-blocking)
  - Only polls RUNNING projects (skip stopped/crashed)
  - asyncio.get_running_loop() instead of deprecated version
"""
from __future__ import annotations

import asyncio
import logging

from database.models import all_projects, log_resources, update_project
from .process_manager import process_manager

log = logging.getLogger(__name__)


async def poll_all_resources() -> None:
    """Periodic job — poll every running project's stats, write to resource_logs."""
    try:
        projects = await all_projects()
    except Exception as exc:
        log.exception("poll_all_resources: db read failed: %s", exc)
        return

    loop = asyncio.get_running_loop()

    for p in projects:
        if p.get("status") != "running":
            continue
        pid = p["project_id"]
        try:
            # get_stats uses psutil in executor internally
            stats = await process_manager.get_stats(pid)
            await log_resources(
                pid,
                ram_mb=float(stats["ram_mb"]),
                cpu_pct=float(stats["cpu_percent"]),
            )
            # If process is no longer running, sync DB
            if stats["status"] not in ("running", "restarting"):
                await update_project(pid, {"status": stats["status"]})
                log.info("poll_all_resources: project %s is now %s, updated DB", pid, stats["status"])
        except Exception as exc:
            log.debug("resource poll error for %s: %s", pid, exc)
