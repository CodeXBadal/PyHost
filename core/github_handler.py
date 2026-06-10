"""Public + private GitHub clone helpers."""
from __future__ import annotations

import asyncio
import os
import re
import shutil
from typing import Tuple

import git

from config import PROJECTS_DIR

_GH_URL_RE = re.compile(
    r"^https?://github\.com/[\w\.\-]+/[\w\.\-]+(\.git)?/?$",
    re.IGNORECASE,
)


def _validate_github_url(url: str) -> bool:
    return bool(_GH_URL_RE.match((url or "").strip()))


async def clone_public(url: str, project_id: str) -> Tuple[bool, str]:
    if not _validate_github_url(url):
        return False, "invalid GitHub URL"
    target = os.path.join(PROJECTS_DIR, project_id)
    if os.path.exists(target):
        shutil.rmtree(target)

    try:
        await asyncio.to_thread(git.Repo.clone_from, url, target, depth=1)
    except Exception as exc:
        return False, f"clone failed: {exc}"
    # nuke .git to keep things small
    git_dir = os.path.join(target, ".git")
    if os.path.isdir(git_dir):
        shutil.rmtree(git_dir, ignore_errors=True)
    return True, ""


async def clone_private(url: str, token: str, project_id: str) -> Tuple[bool, str]:
    if not _validate_github_url(url):
        return False, "invalid GitHub URL"
    # build authenticated url. NOTE: token is wiped after this call returns.
    if "://" not in url:
        return False, "url must be https"
    auth_url = url.replace("https://", f"https://x-access-token:{token}@", 1)
    target = os.path.join(PROJECTS_DIR, project_id)
    if os.path.exists(target):
        shutil.rmtree(target)
    try:
        await asyncio.to_thread(git.Repo.clone_from, auth_url, target, depth=1)
    except Exception as exc:
        return False, f"clone failed: {exc}"
    # remove .git so the PAT isn't persisted in git remote config
    git_dir = os.path.join(target, ".git")
    if os.path.isdir(git_dir):
        shutil.rmtree(git_dir, ignore_errors=True)
    return True, ""
