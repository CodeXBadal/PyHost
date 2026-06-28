"""Install requirements.txt for the project using a per-project virtualenv.

Each project gets its own isolated `.venv` created with the *exact* python
version the user selected (e.g. python3.11).  This means:
  • packages installed by one user never leak into another project
  • the correct interpreter is used when the project is started
"""
from __future__ import annotations

import logging
import os
from typing import Tuple

from config import PROJECTS_DIR
from .process_manager import process_manager as docker_manager, _find_python
from .file_handler import project_path, read_requirements

log = logging.getLogger(__name__)

VENV_DIR    = ".venv"
VENV_PIP    = os.path.join(VENV_DIR, "bin", "pip")
VENV_PYTHON = os.path.join(VENV_DIR, "bin", "python")


def _proj_dir(project_id: str,
              user_id: int | str | None = None,
              name: str | None = None) -> str:
    return project_path(project_id, user_id, name)


def venv_python_for(project_id: str,
                    user_id: int | str | None = None,
                    name: str | None = None) -> str:
    return os.path.join(_proj_dir(project_id, user_id, name), VENV_PYTHON)


def venv_pip_for(project_id: str,
                 user_id: int | str | None = None,
                 name: str | None = None) -> str:
    return os.path.join(_proj_dir(project_id, user_id, name), VENV_PIP)


async def ensure_venv(project_id: str,
                      python_version: str | None = None,
                      user_id: int | str | None = None,
                      name: str | None = None) -> Tuple[bool, str]:
    """Create the project's .venv with the correct python version if needed.

    If the venv already exists it is reused (no rebuild).
    """
    venv_py = venv_python_for(project_id, user_id, name)
    if os.path.isfile(venv_py):
        return True, ""  # already created

    # Pick the interpreter that matches the user's chosen version
    python_bin = _find_python(python_version)
    proj_dir   = _proj_dir(project_id, user_id, name)

    log.info("Creating venv for project %s with %s", project_id, python_bin)
    code, output = await docker_manager.exec_command(
        project_id,
        f"{python_bin} -m venv {VENV_DIR}",
        workdir=proj_dir,
        user_id=user_id,
        proj_name=name,
    )
    if code != 0:
        log.warning("venv creation failed for %s: %s", project_id, output)
        return False, output

    log.info("venv ready for project %s (%s)", project_id, python_bin)
    return True, ""


async def install_dependencies(project_id: str,
                                python_version: str | None = None,
                                user_id: int | str | None = None,
                                name: str | None = None) -> Tuple[bool, str, list[str]]:
    """Create venv (if needed) then pip-install requirements.txt.

    Returns (success, output, package_list).
    """
    packages = read_requirements(project_id, user_id, name)
    if not packages:
        return False, "no requirements.txt found in project", []

    ok, venv_err = await ensure_venv(project_id, python_version, user_id, name)
    if not ok:
        return False, f"failed to create virtualenv: {venv_err}", packages

    pip_bin  = venv_pip_for(project_id, user_id, name)
    proj_dir = _proj_dir(project_id, user_id, name)

    log.info("Installing deps for project %s via %s", project_id, pip_bin)
    code, output = await docker_manager.exec_command(
        project_id,
        f"{pip_bin} install --no-cache-dir --disable-pip-version-check -r requirements.txt",
        workdir=proj_dir,
        user_id=user_id,
        proj_name=name,
    )
    return code == 0, output, packages
