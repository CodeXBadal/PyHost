"""Install requirements.txt inside the project container."""
from __future__ import annotations

import logging
from typing import Tuple

from .docker_manager import docker_manager
from .file_handler import read_requirements

log = logging.getLogger(__name__)


async def install_dependencies(project_id: str) -> Tuple[bool, str, list[str]]:
    """
    Run `pip install -r requirements.txt` inside the container.
    Returns (success, output, package_list).
    """
    packages = read_requirements(project_id)
    if not packages:
        return False, "no requirements.txt", []

    # Ensure the container is running so we can exec pip inside it
    name = docker_manager._container_name(project_id)
    try:
        cont = await docker_manager._to_thread(docker_manager.client.containers.get, name)
        await docker_manager._to_thread(cont.start)
    except Exception:
        pass

    code, output = await docker_manager.exec_command(
        project_id,
        "pip install --no-cache-dir --disable-pip-version-check -r requirements.txt",
    )
    return code == 0, output, packages
