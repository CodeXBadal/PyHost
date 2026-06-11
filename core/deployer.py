"""
Deploy pipeline orchestrator: scan → create container → record project.
"""
from __future__ import annotations

import logging
from typing import Dict, Tuple

from database.models import create_project, get_or_create_user
from .process_manager import process_manager as docker_manager
from .security import scan_project

log = logging.getLogger(__name__)


async def run_security_scan(project_dir: str):
    return scan_project(project_dir)


async def finalize_deploy(user_id: int, name: str, python_version: str) -> Dict:
    """Create the project DB row + a (stopped) container, return the project."""
    user = await get_or_create_user(user_id, None)
    project = await create_project(user_id, name, python_version)
    try:
        cont_id = await docker_manager.create_container(
            project["project_id"], python_version, plan=user.get("plan", "free"),
        )
        project["container_id"] = cont_id
    except Exception as exc:
        log.exception("docker create failed: %s", exc)
    return project
