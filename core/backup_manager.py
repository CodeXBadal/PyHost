"""ZIP backup / restore for a project's source files."""
from __future__ import annotations

import os
import shutil
import zipfile
from datetime import datetime
from pathlib import PurePosixPath
from typing import Tuple

from config import BACKUP_DIR
from .file_handler import project_path, clear_project_dir


def backup_path(project_id: str, name: str) -> str:
    pid_dir = os.path.join(BACKUP_DIR, project_id)
    os.makedirs(pid_dir, exist_ok=True)
    stamp = datetime.now().strftime("%d%b-%H%M")
    return os.path.join(pid_dir, f"{name}-backup-{stamp}.zip")


def create_backup(project_id: str, project_name: str,
                   user_id=None, name=None) -> Tuple[str, int]:
    src = project_path(project_id, user_id, name)
    zip_path = backup_path(project_id, project_name)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(src):
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, src)
                zf.write(full, rel)
    size = os.path.getsize(zip_path)
    return zip_path, size


def _zip_member_is_safe(name: str) -> bool:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute():
        return False
    return all(part not in ("..", "") for part in path.parts)


def restore_backup(project_id: str, zip_path: str,
                    user_id=None, name=None) -> Tuple[bool, str]:
    if not os.path.isfile(zip_path):
        return False, "backup not found"
    if not zipfile.is_zipfile(zip_path):
        return False, "not a valid zip"
    target = project_path(project_id, user_id, name)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                if not _zip_member_is_safe(member.filename):
                    return False, f"unsafe path in backup: {member.filename}"
            clear_project_dir(project_id, user_id, name)
            zf.extractall(target)
    except Exception as exc:
        return False, f"restore failed: {exc}"
    return True, ""


def delete_backup_file(path: str) -> bool:
    try:
        if os.path.exists(path):
            os.remove(path)
        return True
    except Exception:
        return False
