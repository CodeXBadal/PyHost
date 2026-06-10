"""Tiny, generic helpers used across the codebase."""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Iterable

PROJECT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-]{1,31}$")


def valid_project_name(name: str) -> bool:
    return bool(PROJECT_NAME_RE.match(name))


def progress_bar(pct: float, width: int = 8) -> str:
    pct = max(0, min(100, pct))
    filled = int(round(pct / 100 * width))
    return "▓" * filled + "░" * (width - filled)


def human_size(num_bytes: float) -> str:
    if num_bytes < 1024:
        return f"{num_bytes:.0f} B"
    for unit in ("KB", "MB", "GB", "TB"):
        num_bytes /= 1024
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
    return f"{num_bytes:.1f} PB"


def human_uptime(seconds: float | None) -> str:
    if not seconds or seconds < 1:
        return "—"
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    mins, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if mins:
        parts.append(f"{mins}m")
    if not parts:
        parts.append(f"{secs}s")
    elif len(parts) < 3:
        parts.append(f"{secs}s")
    return " ".join(parts)


def fmt_time(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%d %b %Y — %H:%M")


def truncate(text: str, limit: int = 3500, tail: bool = True) -> str:
    if len(text) <= limit:
        return text
    if tail:
        return "...\n" + text[-(limit - 4):]
    return text[: limit - 4] + "..."


def chunked(iterable: Iterable, size: int):
    chunk = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk
