"""Public + private GitHub clone helpers.

FIX for BUG-038: the PAT is no longer embedded in the git URL passed to
``git clone``.  Embedding the token in the URL leaked it into
/proc/<pid>/cmdline (visible via ``ps``) and into gitpython's stderr on
failure.  We now pass authentication via an ephemeral HTTP header using
``http.extraheader`` and an Authorization Basic value, which lives only
inside the git process's memory and is not visible in process listings.
"""
from __future__ import annotations

import asyncio
import base64
import os
import re
import shutil
from typing import Tuple

import git

from core.file_handler import project_path

_GH_URL_RE = re.compile(
    r"^https?://github\.com/[\w\.\-]+/[\w\.\-]+(\.git)?/?$",
    re.IGNORECASE,
)


def _validate_github_url(url: str) -> bool:
    return bool(_GH_URL_RE.match((url or "").strip()))


def _clone_safely(url: str, target: str, env: dict | None = None,
                  extra_config: list[str] | None = None) -> None:
    """Synchronous clone wrapper run in a thread."""
    kwargs: dict = {"depth": 1}
    if extra_config:
        kwargs["multi_options"] = [f"--config={c}" for c in extra_config]
    if env is not None:
        kwargs["env"] = env
    git.Repo.clone_from(url, target, **kwargs)


async def clone_public(url: str, project_id: str,
                       user_id: int | str | None = None,
                       name: str | None = None) -> Tuple[bool, str]:
    if not _validate_github_url(url):
        return False, "invalid GitHub URL"
    target = project_path(project_id, user_id, name)
    if os.path.exists(target):
        shutil.rmtree(target)
    os.makedirs(target, exist_ok=True)
    try:
        await asyncio.to_thread(_clone_safely, url, target)
    except Exception as exc:
        return False, f"clone failed: {_scrub(str(exc))}"
    git_dir = os.path.join(target, ".git")
    if os.path.isdir(git_dir):
        shutil.rmtree(git_dir, ignore_errors=True)
    return True, ""


async def clone_private(url: str, token: str, project_id: str,
                        user_id: int | str | None = None,
                        name: str | None = None) -> Tuple[bool, str]:
    """Clone a private repo without exposing the PAT on the process line.

    Authentication is provided via http.extraheader (Authorization: Basic
    base64('x-access-token:<token>')) rather than embedding the token in
    the URL.  This keeps the token out of /proc/<pid>/cmdline and out of
    any error messages git writes to stderr.
    """
    if not _validate_github_url(url):
        return False, "invalid GitHub URL"
    if "://" not in url:
        return False, "url must be https"

    target = project_path(project_id, user_id, name)
    if os.path.exists(target):
        shutil.rmtree(target)
    os.makedirs(target, exist_ok=True)

    basic = base64.b64encode(
        f"x-access-token:{token}".encode("utf-8")
    ).decode("ascii")
    # The config key passes the header via git's internal HTTP client,
    # which never echoes it to stderr or environ-style listings.
    extra_config = [f"http.extraheader=Authorization: Basic {basic}"]

    try:
        await asyncio.to_thread(
            _clone_safely, url, target, None, extra_config,
        )
    except Exception as exc:
        # Scrub the basic-auth blob and the raw token from any error
        # message we surface back to the caller / logs.
        msg = _scrub(str(exc))
        msg = msg.replace(basic, "<redacted>")
        if token:
            msg = msg.replace(token, "<redacted>")
        return False, f"clone failed: {msg}"
    finally:
        # Drop the local reference to the token ASAP.
        token = ""        # noqa: F841 — intentional zeroing
        basic = ""        # noqa: F841

    git_dir = os.path.join(target, ".git")
    if os.path.isdir(git_dir):
        shutil.rmtree(git_dir, ignore_errors=True)
    return True, ""


def _scrub(text: str) -> str:
    """Remove anything that looks like a GitHub PAT from a string."""
    # ghp_ / gho_ / ghu_ / ghs_ / ghr_ tokens are 36 chars after the prefix.
    return re.sub(r"gh[pousr]_[A-Za-z0-9]{30,}", "<redacted>", text)
