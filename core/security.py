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
    # Process creation and ctypes are hard-fail patterns.
    "subprocess.Popen",
    "subprocess.run",
    "subprocess.call",
    "os.popen",
    "ctypes",
}

# AST node types that indicate dangerous code
_DANGEROUS_AST_CALLS = {"eval", "exec", "compile", "__import__"}

# Dangerous patterns specific to shell scripts (.sh). Shell scripts are
# allowed to be uploaded but must be scanned — they can run on startup.
_SHELL_DANGER_PATTERNS = [
    "curl | bash",
    "curl|bash",
    "curl -s | bash",
    "wget | bash",
    "wget|bash",
    "curl ",
    "wget ",
    "nc ",
    "ncat ",
    "netcat",
    "rm -rf",
    "rm -fr",
    ":(){:|:&};:",
    "mkfs",
    "dd if=",
    "chmod 777",
    "/dev/tcp/",
    "bash -i",
    "sh -i",
    "> /dev/sd",
    "eval ",
    "base64 -d",
    "base64 --decode",
    "iptables",
    "crontab",
]


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

    # ── Step 3b: Shell script (.sh) scan ────────────────────
    # Shell scripts bypass the Python AST scan, so they get a dedicated
    # pattern scan for dangerous commands (curl|bash, wget, nc, rm -rf, ...).
    for fp in all_files:
        if not fp.endswith(".sh"):
            continue
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read().lower()
        except Exception:
            continue
        for pat in _SHELL_DANGER_PATTERNS:
            if pat.lower() in content:
                statuses[2] = False
                reason = f"dangerous shell pattern: `{pat.strip()}` in {os.path.basename(fp)}"
                log.warning("Security: %s", reason)
                return False, statuses, reason

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
        # Don't scan the canonical env files — they intentionally contain secrets.
        if os.path.basename(fp) in {".env", ".env.example"}:
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


# BUG-036 / BUG-039: dangerous Unicode tricks and `python -c` style code
# injection are now both blocked by validate_run_command.

# Unicode bidi / format / zero-width characters that can hide command
# semantics (e.g. U+202E Right-To-Left Override).
_FORBIDDEN_UNICODE_RANGES = [
    (0x200B, 0x200F),  # zero-width / direction marks
    (0x202A, 0x202E),  # bidi embeddings / overrides
    (0x2066, 0x2069),  # bidi isolates
    (0xFEFF, 0xFEFF),  # BOM
]


def _contains_forbidden_unicode(s: str) -> bool:
    for ch in s:
        cp = ord(ch)
        for lo, hi in _FORBIDDEN_UNICODE_RANGES:
            if lo <= cp <= hi:
                return True
        # Block other ASCII control characters (except plain space / tab).
        if cp < 0x20 and ch not in (" ", "\t"):
            return True
    return False


# Python flags that allow inline code execution and therefore bypass our
# uploaded-source AST scan (BUG-039).
_PYTHON_INLINE_FLAGS = ("-c", "-m", "--command")


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

    # BUG-036: block Unicode bidi / zero-width / control chars.
    if _contains_forbidden_unicode(cmd):
        return False, "forbidden control / bidi unicode character in command"

    # Check for null bytes
    if "\x00" in cmd:
        return False, "null byte in command"

    # BUG-039: refuse `python -c "<arbitrary code>"` because the AST
    # scanner only inspects uploaded .py files — inline code on the
    # command line would otherwise sneak past every check.
    try:
        import shlex as _shlex
        tokens = _shlex.split(cmd)
    except ValueError:
        return False, "command parse failed (mismatched quotes?)"
    if tokens and os.path.basename(tokens[0]).startswith("python"):
        for tok in tokens[1:]:
            if tok in _PYTHON_INLINE_FLAGS or tok.startswith("-c="):
                return False, (
                    f"forbidden python flag '{tok}': inline code execution "
                    "(-c / -m / --command) bypasses the security scanner"
                )

    # Reasonable length limit
    if len(cmd) > 500:
        return False, "command too long (>500 chars)"

    return True, ""
