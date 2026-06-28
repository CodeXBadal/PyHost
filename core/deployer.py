"""
Deploy pipeline orchestrator: create project dir → create venv → record in DB.

FIX for BUG-004: we import `process_manager` directly (not as an aliased
`docker_manager`) so it is obvious which backend is in use and so that
swapping in the Docker-based `DockerManager` will not silently fail with
TypeError on unexpected kwargs.  The Docker backend's `create_container`
signature also accepts ``user_id`` / ``name`` defensively (see
core/docker_manager.py).

FIX for BUG-024: source code is now moved BEFORE the venv is created
(see handlers/new_project.py state_python_version), so the venv is built
inside the populated project directory and subsequent redeploys cannot
overwrite it.
"""
from __future__ import annotations

import logging
from typing import Dict

from database.models import create_project, get_or_create_user
from .process_manager import process_manager
from .security import scan_project
from .dependency_installer import ensure_venv

log = logging.getLogger(__name__)


async def run_security_scan(project_dir: str):
    return scan_project(project_dir)


async def finalize_deploy(user_id: int, name: str, python_version: str) -> Dict:
    """Create the project DB row and project directory.

    NOTE: the venv is now created AFTER source code is moved into the
    project directory (see handlers/new_project.py).  Do not move it back
    into this function — that re-introduces BUG-024.
    """
    user    = await get_or_create_user(user_id, None)
    project = await create_project(user_id, name, python_version)
    pid     = project["project_id"]

    try:
        await process_manager.create_container(
            pid, python_version,
            plan=user.get("plan", "free"),
            user_id=user_id,
            name=name,
        )
        project["container_id"] = pid
    except TypeError as exc:
        # If a different backend (DockerManager) is wired in that does
        # NOT yet accept user_id / name kwargs, fall back gracefully.
        log.warning("create_container TypeError (signature mismatch): %s", exc)
        try:
            await process_manager.create_container(
                pid, python_version, plan=user.get("plan", "free"),
            )
            project["container_id"] = pid
        except Exception as exc2:
            log.exception("create_container fallback failed: %s", exc2)
    except Exception as exc:
        log.exception("create_container failed: %s", exc)

    return project


async def ensure_project_venv(project_id: str, user_id: int, name: str,
                              python_version: str) -> None:
    """Create the venv inside an already-populated project directory.

    Called from handlers/new_project.py AFTER the source code has been
    moved into the canonical projects/<user_id>/<name>/ directory.  This
    ordering fix is BUG-024.
    """
    try:
        ok, err = await ensure_venv(
            project_id,
            python_version=python_version,
            user_id=user_id,
            name=name,
        )
        if not ok:
            log.warning("venv creation failed for %s (version %s): %s",
                        project_id, python_version, err)
        else:
            log.info("venv (python%s) ready for project %s", python_version, project_id)
    except Exception as exc:
        log.exception("ensure_venv failed for %s: %s", project_id, exc)
