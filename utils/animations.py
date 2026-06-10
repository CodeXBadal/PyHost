"""
Reusable animated message sequences via edit_message_text.

Each function takes a Telegram `Message` (the one to edit) and progresses
through a series of frames with small asyncio.sleep delays.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Iterable, List

from telegram import Message
from telegram.error import BadRequest

log = logging.getLogger(__name__)


async def _safe_edit(msg: Message, text: str) -> None:
    try:
        await msg.edit_text(text, parse_mode="Markdown")
    except BadRequest as exc:
        if "not modified" in str(exc).lower():
            return
        # parse-mode error fallback → plain text
        try:
            await msg.edit_text(text)
        except Exception:
            pass
    except Exception as exc:
        log.debug("edit_text suppressed: %s", exc)


# ────────────────────────────────────────────────────────────
# Upload animation (3 frames)
# ────────────────────────────────────────────────────────────
async def upload_progress(msg: Message) -> None:
    await _safe_edit(msg, "📤 *Uploading your file...*\n`[▓▓▓░░░░░░░] 30%`")
    await asyncio.sleep(0.5)
    await _safe_edit(msg, "📤 *Uploading your file...*\n`[▓▓▓▓▓▓░░░░] 60%`")
    await asyncio.sleep(0.5)
    await _safe_edit(msg, "📤 *Upload complete!*\n🔍 Scanning files for security...")
    await asyncio.sleep(0.4)


# ────────────────────────────────────────────────────────────
# 6-step security scan animation
# ────────────────────────────────────────────────────────────
SCAN_STEPS: List[str] = [
    "Checking file types",
    "Checking for malware",
    "Checking dangerous code",
    "Run command check",
    "Secrets scanner",
    "Validating structure",
]


async def scan_animation(msg: Message, statuses: Iterable[bool] | None = None) -> None:
    """
    Render the 6-step scan animation; if statuses is None all 6 pass.
    statuses: iterable of 6 booleans in step order (True = ✅, False = ❌).
    """
    statuses = list(statuses) if statuses else [True] * 6
    for i in range(len(SCAN_STEPS)):
        lines = ["🔍 *Scanning files...*", ""]
        for j, step in enumerate(SCAN_STEPS):
            if j < i:
                mark = "✅" if statuses[j] else "❌"
            elif j == i:
                mark = "⏳"
            else:
                mark = " "
            lines.append(f"━ {step:<28} {mark}")
        await _safe_edit(msg, "\n".join(lines))
        await asyncio.sleep(0.35)

    # final frame
    final_lines = ["🔍 *Scanning files...*", ""]
    for j, step in enumerate(SCAN_STEPS):
        mark = "✅" if statuses[j] else "❌"
        final_lines.append(f"━ {step:<28} {mark}")
    passed = sum(1 for s in statuses if s)
    if passed == 6:
        final_lines.append("")
        final_lines.append(f"✅ *All checks passed! ({passed}/6)*\nEverything looks safe!")
    else:
        final_lines.append("")
        final_lines.append(f"❌ *Scan failed ({passed}/6)*")
    await _safe_edit(msg, "\n".join(final_lines))


# ────────────────────────────────────────────────────────────
# Deploy animation (4 frames)
# ────────────────────────────────────────────────────────────
async def deploy_animation(msg: Message, python_version: str = "3.12") -> None:
    frames = [
        "🐳 *Creating Docker container...*",
        f"🐳 *Setting up Python {python_version} environment...*",
        "🔒 *Applying security policies...*",
        "✅ *Container ready!*",
    ]
    for f in frames:
        await _safe_edit(msg, f)
        await asyncio.sleep(0.5)


# ────────────────────────────────────────────────────────────
# Per-package install animation
# ────────────────────────────────────────────────────────────
async def install_progress(msg: Message, packages: List[str]) -> None:
    """Show packages one by one being checked off."""
    statuses = ["⏳"] * len(packages)
    for i in range(len(packages)):
        statuses[i] = "✅"
        body = "\n".join(f"━ {pkg:<35} {st}" for pkg, st in zip(packages, statuses))
        await _safe_edit(msg, f"📦 *Installing...*\n```\n{body}\n```")
        await asyncio.sleep(0.4)


# ────────────────────────────────────────────────────────────
# Deletion animation
# ────────────────────────────────────────────────────────────
async def delete_animation(msg: Message) -> None:
    steps = [
        ("Stopping container",   True),
        ("Removing files",       True),
        ("Deleting error logs",  True),
        ("Cleaning database",    True),
    ]
    cumulative: List[str] = ["🗑️ *Deleting project...*"]
    for label, _ok in steps:
        cumulative.append(f"━ {label:<22} ⏳")
        await _safe_edit(msg, "\n".join(cumulative))
        await asyncio.sleep(0.3)
        cumulative[-1] = f"━ {label:<22} ✅"
        await _safe_edit(msg, "\n".join(cumulative))
        await asyncio.sleep(0.2)
    cumulative.append("\n✅ *Project deleted successfully.*")
    await _safe_edit(msg, "\n".join(cumulative))
