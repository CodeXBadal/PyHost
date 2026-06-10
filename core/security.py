"""
Security scanner — 7-step pipeline that runs over an extracted
project directory before it's allowed to deploy.

Returns a (passed, statuses, reason) tuple:
    passed   : bool — overall pass/fail
    statuses : list[bool] — exactly 6 booleans, one per visible scan step
    reason   : str  — human-readable failure reason (empty on success)
"""
from __future__ import annotations

import logging
import os
from typing import List, Tuple

from config import (
    ALLOWED_FILE_EXTENSIONS, DANGER_PATTERNS,
    MAX_PROJECT_SIZE_MB, MAX_SINGLE_FILE_MB,
    RUN_CMD_BLOCK_CHARS,
)

log = logging.getLogger(__name__)

# Stock “known-malware” pattern set (lightweight; substring match).
MALWARE_PATTERNS = [
    "nc -e",
    "bash -i >&",
    "/dev/tcp/",
    "stratum+tcp",        # crypto miner
    "minerd",
    "xmrig",
    "powershell -nop -w hidden",
    "curl http://evil",
]

SECRET_PATTERNS = [
    "AKIA",                          # AWS access key id
    "sk_live_",                      # Stripe
    "AIza",                          # Google API
    "ghp_",                          # GitHub PAT
]


def _walk_files(root: str):
    for dirpath, _dirs, files in os.walk(root):
        # skip .git
        if ".git" in dirpath.split(os.sep):
            continue
        for f in files:
            yield os.path.join(dirpath, f)


def scan_project(project_dir: str) -> Tuple[bool, List[bool], str]:
    """6 displayed scan steps; returns aggregated pass/fail + per-step statuses."""
    statuses: List[bool] = [True] * 6
    reason = ""

    if not os.path.isdir(project_dir):
        return False, [False] * 6, "project directory missing"

    all_files = list(_walk_files(project_dir))
    total_size = 0

    # ── Step 1: file types ─────────────────────────────────
    for fp in all_files:
        ext = os.path.splitext(fp)[1].lower()
        if ext and ext not in ALLOWED_FILE_EXTENSIONS:
            # allow files w/o extension only if at root (e.g. Dockerfile, README)
            if ext == "" and os.path.dirname(fp) == project_dir:
                continue
            statuses[0] = False
            reason = f"disallowed file extension: {os.path.basename(fp)}"
            log.warning("Security: %s", reason)
            return False, statuses, reason

    # ── Step 2: malware patterns ───────────────────────────
    for fp in all_files:
        try:
            sz = os.path.getsize(fp)
            total_size += sz
            if sz > MAX_SINGLE_FILE_MB * 1024 * 1024:
                statuses[1] = False
                return False, statuses, f"file too large: {os.path.basename(fp)} ({sz/1024/1024:.1f} MB)"
        except OSError:
            continue
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read(MAX_SINGLE_FILE_MB * 1024 * 1024)
        except Exception:
            continue
        for pat in MALWARE_PATTERNS:
            if pat in content:
                statuses[1] = False
                return False, statuses, f"malware pattern detected: {pat}"

    if total_size > MAX_PROJECT_SIZE_MB * 1024 * 1024:
        statuses[1] = False
        return False, statuses, f"total project size {total_size/1024/1024:.1f} MB exceeds {MAX_PROJECT_SIZE_MB} MB"

    # ── Step 3: dangerous code patterns ────────────────────
    for fp in all_files:
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
        except Exception:
            continue
        for pat in DANGER_PATTERNS:
            if pat in content:
                # Note: we only HARD-FAIL on the worst patterns. Some (eval/exec)
                # are common in libraries — warn but allow.
                if pat in ("rm -rf", "chmod 777", ":(){:|:&};:",
                           "__import__('os')", "__import__(\"os\")"):
                    statuses[2] = False
                    return False, statuses, f"dangerous pattern: {pat} in {os.path.basename(fp)}"
                log.info("Security: suspicious pattern '%s' in %s (allowed with warning)",
                         pat, os.path.basename(fp))

    # ── Step 4: run command check (deferred — done at deploy) ─
    # The actual command is validated by validate_run_command() at config time.

    # ── Step 5: secrets scanner (warn-only) ────────────────
    for fp in all_files:
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
        except Exception:
            continue
        for pat in SECRET_PATTERNS:
            if pat in content:
                log.info("Security: possible hardcoded secret pattern '%s' in %s",
                         pat, os.path.basename(fp))

    # ── Step 6: validate structure ─────────────────────────
    py_files = [f for f in all_files if f.endswith(".py")]
    if not py_files:
        statuses[5] = False
        return False, statuses, "no Python files found in project"

    return True, statuses, ""


def validate_run_command(cmd: str) -> Tuple[bool, str]:
    """Return (ok, reason)."""
    cmd = (cmd or "").strip()
    if not cmd:
        return False, "empty"
    if not cmd.startswith(("python", "uvicorn", "gunicorn", "flask")):
        return False, "command must start with python / uvicorn / gunicorn / flask"
    for blocked in RUN_CMD_BLOCK_CHARS:
        if blocked in cmd:
            return False, f"forbidden character '{blocked}'"
    return True, ""
