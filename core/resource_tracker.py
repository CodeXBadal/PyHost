"""APScheduler-driven RAM/CPU/uptime polling for every running project."""
from __future__ import annotations

import logging

from database.models import all_projects, log_resources, update_project
from .process_manager import process_manager as docker_manager

log = logging.getLogger(__name__)


async def poll_all_resources() -> None:
    """Periodic job — poll every project's container, write to resource_logs."""
    try:
        projects = await all_projects()
    except Exception as exc:
        log.exception("poll_all_resources: db read failed: %s", exc)
        return

    for p in projects:
        if p.get("status") != "running":
            continue
        try:
            stats = await docker_manager.get_stats(p["project_id"])
            await log_resources(
                p["project_id"],
                ram_mb=float(stats["ram_mb"]),
                cpu_pct=float(stats["cpu_percent"]),
            )
            # If docker says the container is no longer running, update DB
            if stats["status"] not in ("running", "restarting"):
                await update_project(p["project_id"], {"status": stats["status"]})
        except Exception as exc:
            log.debug("resource poll error for %s: %s", p["project_id"], exc)
