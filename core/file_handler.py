"""ZIP extraction + single .py handling for project source uploads.

Directory layout
----------------
user_data/
└── projects/
    └── <user_id>/          ← one folder per Telegram user
        └── <project_name>/ ← one folder per project (human-readable)
            ├── main.py
            ├── requirements.txt
            ├── .venv/
            ├── .pyhost.pid
            └── .pyhost.log

`project_path(project_id, user_id, name)` is the canonical way to resolve
the on-disk path.  project_id is still the primary DB key; user_id + name
decide the filesystem location.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import unicodedata
import zipfile
from typing import List, Tuple

import aiofiles

from config import MAX_PROJECT_SIZE_MB, PROJECTS_DIR

log = logging.getLogger(__name__)

# ── Junk files/folders inject kiya macOS/Windows tools by — ignore karo ──────
_JUNK_NAMES = {
    "__MACOSX",
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    ".Spotlight-V100",
    ".Trashes",
    ".fseventsd",
}


# ── Path helpers ─────────────────────────────────────────────

def project_path(project_id: str,
                 user_id: int | str | None = None,
                 name: str | None = None) -> str:
    """Return (and create) the on-disk directory for a project.

    Two calling conventions:
      • project_path(project_id, user_id, name)  → new-style  projects/<uid>/<name>/
      • project_path(project_id)                 → legacy     projects/<project_id>/
        (used during the pending/tmp phase before the project is committed to DB)
    """
    if user_id is not None and name is not None:
        p = os.path.join(PROJECTS_DIR, str(user_id), _safe_dirname(name))
    else:
        p = os.path.join(PROJECTS_DIR, project_id)
    os.makedirs(p, exist_ok=True)
    return p


def _safe_dirname(name: str) -> str:
    """Sanitise a project name so it's safe to use as a directory name.

    FIX for BUG-043: when the sanitised name exceeds 64 characters we now
    append a short hash of the ORIGINAL name before truncating, so two
    distinct project names that differ only in the >64th character no
    longer collide on disk.
    """
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    if not safe:
        return "project"
    if len(safe) <= 64:
        return safe
    # 8-char hex digest of the raw input gives 2^32 distinct buckets,
    # far more than the number of projects per user.
    h = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    # 55 + 1 + 8 = 64 characters max.
    return f"{safe[:55]}_{h}"


def clear_project_dir(project_id: str,
                      user_id: int | str | None = None,
                      name: str | None = None) -> None:
    p = project_path(project_id, user_id, name)
    if os.path.exists(p):
        shutil.rmtree(p)
    os.makedirs(p, exist_ok=True)


async def save_uploaded_file(file_bytes: bytes, filename: str, dest_dir: str) -> str:
    os.makedirs(dest_dir, exist_ok=True)
    full = os.path.join(dest_dir, filename)
    async with aiofiles.open(full, "wb") as f:
        await f.write(file_bytes)
    return full


# ── Junk cleaner ─────────────────────────────────────────────

def _remove_junk(target_dir: str) -> None:
    """macOS __MACOSX, .DS_Store, Windows Thumbs.db etc. hata do."""
    for item in os.listdir(target_dir):
        if item in _JUNK_NAMES or item.startswith("._"):
            full = os.path.join(target_dir, item)
            try:
                if os.path.isdir(full):
                    shutil.rmtree(full)
                else:
                    os.remove(full)
                log.debug("Removed junk: %s", full)
            except Exception as e:
                log.warning("Could not remove junk %s: %s", full, e)


# ── Smart flatten ─────────────────────────────────────────────

def _flatten_if_needed(target_dir: str) -> None:
    """
    Agar saari files ek wrapper folder ke andar hain to flatten karo.

    Handle karta hai:
      - Single top-level folder:   MyProject/main.py  →  main.py
      - Double nested:             MyProject/MyProject/main.py  →  main.py
      - macOS junk + folder:       __MACOSX/ + MyProject/main.py  →  main.py
      - Already flat:              main.py directly  →  kuch nahi karna
      - Multiple folders at root:  src/ + tests/ + main.py  →  kuch nahi karna (sahi hai)

    Loop chalata hai jab tak structure flat na ho jaye.
    """
    while True:
        # Pehle junk saaf karo taaki woh count mein na aaye
        _remove_junk(target_dir)

        # Hidden files (.git, .env etc.) ko chhod ke real items dekho
        real_items = [
            i for i in os.listdir(target_dir)
            if not i.startswith(".")
        ]

        # Agar sirf 1 item hai aur wo folder hai — flatten karo
        if len(real_items) != 1:
            break  # Multiple items ya empty — structure sahi hai

        only = os.path.join(target_dir, real_items[0])
        if not os.path.isdir(only):
            break  # Single file hai — flatten ki zaroorat nahi

        log.debug("Flattening wrapper folder: %s", only)

        # Folder ke andar sab kuch ek level upar move karo
        for entry in os.listdir(only):
            src = os.path.join(only, entry)
            dst = os.path.join(target_dir, entry)
            # Conflict hone par purani file/folder hata do
            if os.path.exists(dst):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                else:
                    os.remove(dst)
            shutil.move(src, dst)

        # Ab khali wrapper folder hata do
        try:
            shutil.rmtree(only)
        except Exception as e:
            log.warning("Could not remove wrapper dir %s: %s", only, e)

        # Loop continue — double/triple nested bhi handle hoga


# ── ZIP extraction ────────────────────────────────────────────

def extract_zip(zip_path: str, target_dir: str) -> Tuple[bool, str]:
    """
    Safe ZIP extraction:
      • No absolute paths
      • No '..' traversal
      • Total uncompressed size <= MAX_PROJECT_SIZE_MB
      • macOS __MACOSX / .DS_Store junk automatically hata deta hai
      • Single (or nested) wrapper folder automatically flatten karta hai
      • requirements.txt kisi bhi nesting level pe mil jaayegi
    """
    if not zipfile.is_zipfile(zip_path):
        return False, "not a zip file"

    os.makedirs(target_dir, exist_ok=True)
    total = 0

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = zf.infolist()

            # FIX for BUG-044: Unicode-canonicalise (NFC) every member
            # name BEFORE inspecting it, so traversal payloads built from
            # non-NFC sequences (e.g. ..\u202E or composed/decomposed
            # variants of "..") cannot evade the check.
            for m in members:
                if m.is_dir():
                    continue
                raw_name = m.filename
                norm = unicodedata.normalize("NFC", raw_name)
                if "\x00" in norm:
                    return False, f"null byte in zip entry name: {raw_name!r}"
                # Reject names containing any C0/C1 control / bidi chars.
                if any(unicodedata.category(c).startswith("C")
                       and c not in ("\t",) for c in norm):
                    return False, f"control character in zip entry name: {raw_name!r}"
                name = norm

                # Path traversal check
                parts = name.replace("\\", "/").split("/")
                if any(p in ("..", "") for p in parts[:-1]):
                    return False, f"unsafe path in zip: {name}"
                if name.startswith(("/", "\\")):
                    return False, f"unsafe absolute path in zip: {name}"

                # Size check
                total += m.file_size
                if total > MAX_PROJECT_SIZE_MB * 1024 * 1024:
                    return False, f"unzipped size > {MAX_PROJECT_SIZE_MB} MB"

            # Sab safe hai — extract karo
            zf.extractall(target_dir)

    except zipfile.BadZipFile:
        return False, "corrupted zip file"
    except Exception as exc:
        return False, f"extract error: {exc}"

    # Junk hata do + flatten karo
    _flatten_if_needed(target_dir)

    # Final check — koi file extract hui?
    if not any(True for _ in _walk_files(target_dir)):
        return False, "zip file is empty"

    log.info("ZIP extracted & flattened to: %s", target_dir)
    return True, ""


# ── File tree walker (internal) ───────────────────────────────

def _walk_files(root: str):
    """Recursively yield all file paths, .git skip karo."""
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in files:
            yield os.path.join(dirpath, f)


# ── Project file tree (for File Manager) ─────────────────────

def list_tree(project_id: str, rel: str = "",
              user_id: int | str | None = None,
              name: str | None = None) -> List[dict]:
    """Yield {name, is_dir, rel_path, size} for the given relative folder."""
    base = os.path.join(project_path(project_id, user_id, name), rel)
    if not os.path.isdir(base):
        return []
    entries = []
    for fname in sorted(os.listdir(base)):
        if fname.startswith(".git"):
            continue
        full   = os.path.join(base, fname)
        is_dir = os.path.isdir(full)
        size   = 0 if is_dir else os.path.getsize(full)
        entries.append({
            "name":     fname,
            "is_dir":   is_dir,
            "rel_path": (rel + "/" + fname).lstrip("/"),
            "size":     size,
        })
    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
    return entries


# ── Safe file path resolver ───────────────────────────────────

def get_file_path(project_id: str, rel_path: str,
                  user_id: int | str | None = None,
                  name: str | None = None) -> str | None:
    """Resolve a relative path safely; returns absolute or None if escape detected."""
    base   = project_path(project_id, user_id, name)
    target = os.path.realpath(os.path.join(base, rel_path))
    if not target.startswith(os.path.realpath(base)):
        return None
    if not os.path.exists(target):
        return None
    return target


# ── Requirements reader ───────────────────────────────────────

def read_requirements(project_id: str,
                      user_id: int | str | None = None,
                      name: str | None = None) -> List[str]:
    """
    Return list of requirement lines.

    requirements.txt ko project root mein dhundta hai.
    Agar nahi mili to subfolders mein bhi dhundta hai (flatten miss hone ka fallback).
    """
    proj_dir = project_path(project_id, user_id, name)

    # Pehle root mein check karo (normal case)
    root_req = os.path.join(proj_dir, "requirements.txt")
    if os.path.isfile(root_req):
        return _parse_requirements(root_req)

    # Fallback: kisi bhi subfolder mein dhundo (nested zip edge case)
    for dirpath, dirs, files in os.walk(proj_dir):
        dirs[:] = [d for d in dirs if d not in {".venv", ".git", "__pycache__"}]
        if "requirements.txt" in files:
            found = os.path.join(dirpath, "requirements.txt")
            log.warning(
                "requirements.txt found in subfolder (not root): %s — "
                "consider re-uploading a properly structured ZIP.",
                os.path.relpath(found, proj_dir),
            )
            return _parse_requirements(found)

    return []  # requirements.txt nahi mili


def _parse_requirements(path: str) -> List[str]:
    """Parse a requirements.txt — blank lines aur comments ignore karo."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return [
                ln.strip()
                for ln in f
                if ln.strip() and not ln.startswith("#")
            ]
    except Exception as e:
        log.error("Could not read requirements.txt at %s: %s", path, e)
        return []
