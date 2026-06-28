"""
Format crash data into a pretty .txt error report ready to send to the user.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Dict, Tuple

from config import ERROR_HINTS

# Patterns for extracting exception class names
_EXC_RE = re.compile(r"\b([A-Z][A-Za-z0-9_]*Error|[A-Z][A-Za-z0-9_]*Exception)\b")


def extract_error_type(traceback_text: str) -> Tuple[str, str]:
    """
    Returns (error_type, last_line). error_type is e.g. 'KeyError'.
    Falls back to 'Error' / last non-empty line if it can't find a class.
    """
    if not traceback_text:
        return "Error", "Container exited unexpectedly"

    # Look at the last non-blank line first (usual format: 'ExceptionType: message')
    lines = [ln.rstrip() for ln in traceback_text.splitlines() if ln.strip()]
    if not lines:
        return "Error", "Container exited unexpectedly"

    last = lines[-1]
    m = re.match(r"^\s*([A-Za-z_][\w\.]*?):", last)
    if m:
        et = m.group(1).split(".")[-1]
        return et, last

    m2 = _EXC_RE.search(last) or _EXC_RE.search(traceback_text)
    if m2:
        return m2.group(1), last
    return "Error", last


def hint_for(error_type: str) -> str:
    return ERROR_HINTS.get(error_type, "Check your code and logs for details.")


def build_report(*,
                 project_name: str,
                 exit_code: int,
                 restart_attempt: int,
                 max_restarts: int,
                 traceback_text: str,
                 ram_mb: float,
                 ram_limit_mb: float,
                 cpu_pct: float,
                 uptime_str: str,
                 ) -> Dict[str, str]:
    """Return a dict with filename, body, error_type, error_line, hint."""
    error_type, error_line = extract_error_type(traceback_text)
    hint = hint_for(error_type)

    now = datetime.now()
    timestamp = now.strftime("%d %b %Y — %H:%M:%S")
    filename = f"{project_name}-error-{now.strftime('%d%b-%H%M')}.txt"

    body = f"""══════════════════════════════════════════
🚨 ERROR REPORT — {project_name}
══════════════════════════════════════════
📅 Time       : {timestamp}
💥 Exit Code  : {exit_code}
🔁 Restarted  : {'Yes' if restart_attempt > 0 else 'No'} (attempt {restart_attempt}/{max_restarts})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 TRACEBACK:
━━━━━━━━━━━━━
{traceback_text or '(no traceback captured)'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 POSSIBLE FIX:
━━━━━━━━━━━━━━━━
{hint}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 STATS AT CRASH:
RAM    : {ram_mb:.0f} MB / {ram_limit_mb:.0f} MB
CPU    : {cpu_pct:.0f}%
Uptime : {uptime_str} before crash
══════════════════════════════════════════
"""
    return {
        "filename":    filename,
        "body":        body,
        "error_type":  error_type,
        "error_line":  error_line,
        "hint":        hint,
    }


def write_report_file(directory: str, filename: str, body: str) -> str:
    os.makedirs(directory, exist_ok=True)
    full = os.path.join(directory, filename)
    with open(full, "w", encoding="utf-8") as f:
        f.write(body)
    return full
