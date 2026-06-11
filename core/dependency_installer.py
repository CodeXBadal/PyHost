"""Install requirements.txt for the project using pip directly."""
from __future__ import annotations

import logging
from typing import Tuple

from .process_manager import process_manager as docker_manager
from .file_handler import read_requirements

log = logging.getLogger(__name__)


async def install_dependencies(project_id: str) -> Tuple[bool, str, list[str]]:
    """
    Run pip install -r requirements.txt inside the project directory.
    Returns (success, output, package_list).
    """
    packages = read_requirements(project_id)
    if not packages:
        return False, "no requirements.txt found in project", []

    code, output = await docker_manager.exec_command(
        project_id,
        "pip install --no-cache-dir --disable-pip-version-check -r requirements.txt",
    )
    return code == 0, output, packages
