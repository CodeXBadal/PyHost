"""ZIP extraction + single .py handling for project source uploads."""
from __future__ import annotations

import os
import shutil
import zipfile
from typing import Tuple

import aiofiles

from config import MAX_PROJECT_SIZE_MB, PROJECTS_DIR


def project_path(project_id: str) -> str:
    p = os.path.join(PROJECTS_DIR, project_id)
    os.makedirs(p, exist_ok=True)
    return p


def clear_project_dir(project_id: str) -> None:
    p = project_path(project_id)
    if os.path.exists(p):
        shutil.rmtree(p)
    os.makedirs(p, exist_ok=True)


async def save_uploaded_file(file_bytes: bytes, filename: str, dest_dir: str) -> str:
    os.makedirs(dest_dir, exist_ok=True)
    full = os.path.join(dest_dir, filename)
    async with aiofiles.open(full, "wb") as f:
        await f.write(file_bytes)
    return full


def extract_zip(zip_path: str, target_dir: str) -> Tuple[bool, str]:
    """
    Safe ZIP extraction:
      • No absolute paths
      • No '..' traversal
      • Total uncompressed size <= MAX_PROJECT_SIZE_MB
      • If a single top-level folder wraps everything, flatten it.
    """
    if not zipfile.is_zipfile(zip_path):
        return False, "not a zip file"

    os.makedirs(target_dir, exist_ok=True)
    total = 0
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = zf.infolist()
            for m in members:
                if m.is_dir():
                    continue
                # path safety
                name = m.filename
                if name.startswith(("/", "\\")) or ".." in name.split("/"):
                    return False, f"unsafe path in zip: {name}"
                total += m.file_size
                if total > MAX_PROJECT_SIZE_MB * 1024 * 1024:
                    return False, f"unzipped size > {MAX_PROJECT_SIZE_MB} MB"
            zf.extractall(target_dir)
    except zipfile.BadZipFile:
        return False, "corrupted zip"
    except Exception as exc:
        return False, f"extract error: {exc}"

    # Flatten if everything is inside one top-level dir
    items = os.listdir(target_dir)
    if len(items) == 1:
        only = os.path.join(target_dir, items[0])
        if os.path.isdir(only):
            for entry in os.listdir(only):
                shutil.move(os.path.join(only, entry), os.path.join(target_dir, entry))
            shutil.rmtree(only)

    return True, ""


def list_tree(project_id: str, rel: str = ""):
    """Yield {name, is_dir, rel_path, size} for the given relative folder."""
    base = os.path.join(project_path(project_id), rel)
    if not os.path.isdir(base):
        return []
    entries = []
    for name in sorted(os.listdir(base)):
        if name.startswith(".git"):
            continue
        full = os.path.join(base, name)
        is_dir = os.path.isdir(full)
        size = 0 if is_dir else os.path.getsize(full)
        entries.append({
            "name":     name,
            "is_dir":   is_dir,
            "rel_path": (rel + "/" + name).lstrip("/"),
            "size":     size,
        })
    # folders first
    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
    return entries


def get_file_path(project_id: str, rel_path: str) -> str | None:
    """Resolve a relative path safely; returns absolute or None if escape detected."""
    base = project_path(project_id)
    target = os.path.realpath(os.path.join(base, rel_path))
    if not target.startswith(os.path.realpath(base)):
        return None
    if not os.path.exists(target):
        return None
    return target


def read_requirements(project_id: str) -> list[str]:
    """Return list of requirement lines (empty if no requirements.txt)."""
    p = os.path.join(project_path(project_id), "requirements.txt")
    if not os.path.isfile(p):
        return []
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
