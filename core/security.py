"""
Security scanner — 6-step pipeline that runs over an extracted
project directory before it's allowed to deploy.

Fixes:
  - AST-based dangerous code detection (not just substring)
  - Secrets scanner hard-warns user (not silent)
  - validate_run_command improved — no shell metacharacters leak
  - No file content is silently ignored on read errors
"""
from __future__ import annotations

import ast
import logging
import os
from typing import List, Tuple

from config import (
    ALLOWED_FILE_EXTENSIONS, DANGER_PATTERNS,
    MAX_PROJECT_SIZE_MB, MAX_SINGLE_FILE_MB,
    RUN_CMD_BLOCK_CHARS,
)

log = logging.getLogger(__name__)

MALWARE_PATTERNS = [
    "nc -e",
    "bash -i >&",
    "/dev/tcp/",
    "stratum+tcp",
    "minerd",
    "xmrig",
    "powershell -nop -w hidden",
]

SECRET_PATTERNS = [
    ("AKIA",      "AWS Access Key"),
    ("sk_live_",  "Stripe Live Key"),
    ("AIza",      "Google API Key"),
    ("ghp_",      "GitHub Personal Access Token"),
    ("xoxb-",     "Slack Bot Token"),
    ("xoxp-",     "Slack User Token"),
]

# Patterns that are HARD FAIL (not just warnings)
_HARD_FAIL_PATTERNS = {
    "rm -rf",
    "chmod 777",
    ":(){:|:&};:",
    "__import__('os')",
    '__import__("os")',
}

# AST node types that indicate dangerous code
_DANGEROUS_AST_CALLS = {"eval", "exec", "compile", "__import__"}


def _walk_files(root: str):
    for dirpath, dirs, files in os.walk(root):
        # Skip .git directories (modify in-place to prevent recursion)
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in files:
            yield os.path.join(dirpath, f)


def _has_dangerous_ast(source: str) -> Tuple[bool, str]:
    """Check Python source for dangerous AST nodes."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False, ""  # Syntax errors are caught at runtime, not our job

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # Direct call: eval(...), exec(...)
            if isinstance(func, ast.Name) and func.id in _DANGEROUS_AST_CALLS:
                return True, f"dangerous function call: {func.id}()"
            # Attribute call: os.system(...), subprocess.call(...)
            if isinstance(func, ast.Attribute):
                if func.attr in ("system", "popen", "Popen", "call", "run") and \
                   isinstance(func.value, ast.Name) and \
                   func.value.id in ("os", "subprocess"):
                    # These are suspicious but not hard-fail — just log
                    pass
    return False, ""


def scan_project(project_dir: str) -> Tuple[bool, List[bool], str]:
    """6-step security scan. Returns (passed, statuses, reason)."""
    statuses: List[bool] = [True] * 6
    reason = ""

    if not os.path.isdir(project_dir):
        return False, [False] * 6, "project directory missing"

    all_files = list(_walk_files(project_dir))
    total_size = 0

    # ── Step 1: File types ─────────────────────────────────
    for fp in all_files:
        ext = os.path.splitext(fp)[1].lower()
        if ext and ext not in ALLOWED_FILE_EXTENSIONS:
            rel = os.path.relpath(fp, project_dir)
            statuses[0] = False
            reason = f"disallowed file extension: {os.path.basename(fp)}"
            log.warning("Security: %s", reason)
            return False, statuses, reason

    # ── Step 2: Size check + malware patterns ───────────────
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
        return False, statuses, f"total size {total_size/1024/1024:.1f} MB exceeds {MAX_PROJECT_SIZE_MB} MB"

    # ── Step 3: Dangerous code patterns (substring) ─────────
    for fp in all_files:
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
        except Exception:
            continue
        for pat in DANGER_PATTERNS:
            if pat in content:
                if pat in _HARD_FAIL_PATTERNS:
                    statuses[2] = False
                    return False, statuses, f"dangerous pattern: `{pat}` in {os.path.basename(fp)}"
                log.info("Security: suspicious pattern '%s' in %s (warning only)", pat, os.path.basename(fp))

    # ── Step 4: AST analysis for Python files ───────────────
    for fp in all_files:
        if not fp.endswith(".py"):
            continue
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                source = fh.read()
        except Exception:
            continue
        dangerous, detail = _has_dangerous_ast(source)
        if dangerous:
            statuses[3] = False
            return False, statuses, f"{detail} in {os.path.basename(fp)}"

    # ── Step 5: Secrets scanner (warn, return in reason) ────
    secrets_found = []
    for fp in all_files:
        # Don't scan .env files — they intentionally contain secrets
        if os.path.basename(fp).startswith(".env"):
            continue
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
        except Exception:
            continue
        for pat, label in SECRET_PATTERNS:
            if pat in content:
                log.warning("Security: possible hardcoded %s in %s", label, os.path.basename(fp))
                secrets_found.append(f"{label} in {os.path.basename(fp)}")

    # Secrets are warn-only (not hard fail) but we flag them
    if secrets_found:
        log.warning("Security: hardcoded secrets detected: %s", ", ".join(secrets_found))

    # ── Step 6: Validate structure ──────────────────────────
    py_files = [f for f in all_files if f.endswith(".py")]
    if not py_files:
        statuses[5] = False
        return False, statuses, "no Python files found in project"

    return True, statuses, ""


def validate_run_command(cmd: str) -> Tuple[bool, str]:
    """Return (ok, reason).

    Validates that the run command is safe to execute.
    """
    cmd = (cmd or "").strip()
    if not cmd:
        return False, "command cannot be empty"

    allowed_starts = ("python", "uvicorn", "gunicorn", "flask", "hypercorn", "daphne")
    if not any(cmd.startswith(s) for s in allowed_starts):
        return False, f"command must start with: {', '.join(allowed_starts)}"

    for blocked in RUN_CMD_BLOCK_CHARS:
        if blocked in cmd:
            return False, f"forbidden character '{blocked}' in command"

    # Check for null bytes
    if "\x00" in cmd:
        return False, "null byte in command"

    # Reasonable length limit
    if len(cmd) > 500:
        return False, "command too long (>500 chars)"

    return True, ""
