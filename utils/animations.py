"""
Reusable animated message sequences via edit_message_text.

Premium UI/UX — redesigned for maximum visual impact in Telegram:
  • Smooth animated spinners
  • Rich gradient-style progress bars  
  • Clean visual hierarchy with box-drawing chars
  • Contextual icons and status messages per stage
"""
from __future__ import annotations

import asyncio
import logging
from typing import Iterable, List, Optional

from telegram import Message
from telegram.constants import ParseMode
from telegram.error import BadRequest

log = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────
# Visual design tokens
# ────────────────────────────────────────────────────────────

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
PULSE_FRAMES   = ["●○○", "○●○", "○○●", "○●○"]
DOTS_FRAMES    = ["   ", ".  ", ".. ", "..."]


def _progress_bar(pct: int, width: int = 14) -> str:
    """Render a rich progress bar:  ██████████░░░░  75%"""
    filled = round(width * pct / 100)
    bar    = "█" * filled + "░" * (width - filled)
    return f"`{bar}` *{pct}%*"


def _spinner(tick: int) -> str:
    return SPINNER_FRAMES[tick % len(SPINNER_FRAMES)]


def _pulse(tick: int) -> str:
    return PULSE_FRAMES[tick % len(PULSE_FRAMES)]


def _dots(tick: int) -> str:
    return DOTS_FRAMES[tick % len(DOTS_FRAMES)]


# ────────────────────────────────────────────────────────────
# Core safe-edit helper
# ────────────────────────────────────────────────────────────

async def _safe_edit(msg: Message, text: str) -> None:
    try:
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    except BadRequest as exc:
        if "not modified" in str(exc).lower():
            return
        try:
            await msg.edit_text(text)
        except Exception:
            pass
    except Exception as exc:
        log.debug("edit_text suppressed: %s", exc)


# ────────────────────────────────────────────────────────────
# Upload animation
# ────────────────────────────────────────────────────────────

UPLOAD_STAGES = [
    (10,  "Connecting to server"),
    (25,  "Preparing transfer"),
    (45,  "Sending chunks"),
    (65,  "Verifying integrity"),
    (80,  "Finalising upload"),
    (100, "Upload complete!"),
]

async def upload_progress(msg: Message) -> None:
    for tick, (pct, label) in enumerate(UPLOAD_STAGES):
        spin = _spinner(tick)
        done = pct == 100
        icon = "✅" if done else "📤"
        bar  = _progress_bar(pct)

        frame = (
            f"{icon} *Uploading your file*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"\n"
            f"{bar}\n"
            f"\n"
            f"`{spin}` _{label}_"
        )
        await _safe_edit(msg, frame)
        await asyncio.sleep(0.4)

    await asyncio.sleep(0.3)


# ────────────────────────────────────────────────────────────
# Security scan animation
# ────────────────────────────────────────────────────────────

SCAN_STEPS: List[str] = [
    "File type validation",
    "Malware detection",
    "Dangerous code analysis",
    "Shell command inspection",
    "Secrets & credentials scan",
    "Structure integrity check",
]

SCAN_ICONS: List[str] = ["📎", "🦠", "💀", "🖥️", "🔑", "🏗️"]

async def scan_animation(msg: Message, statuses: Iterable[bool] | None = None) -> None:
    statuses = list(statuses) if statuses else [True] * 6

    for tick, i in enumerate(range(len(SCAN_STEPS))):
        spin  = _spinner(tick * 3)
        lines = [
            "🔐 *Security Scan*",
            "━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
        ]
        for j, (step, icon) in enumerate(zip(SCAN_STEPS, SCAN_ICONS)):
            if j < i:
                mark = "✅" if statuses[j] else "❌"
            elif j == i:
                mark = f"`{spin}`"
            else:
                mark = "⬜"
            lines.append(f"{icon}  {step:<32} {mark}")

        pct = round((i / len(SCAN_STEPS)) * 100)
        lines += ["", _progress_bar(pct), ""]
        lines.append(f"_Analysing… step {i + 1}/{len(SCAN_STEPS)}_")

        await _safe_edit(msg, "\n".join(lines))
        await asyncio.sleep(0.35)

    # ── Final frame ──
    passed = sum(1 for s in statuses if s)
    final  = [
        "🔐 *Security Scan*",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    for j, (step, icon) in enumerate(zip(SCAN_STEPS, SCAN_ICONS)):
        mark = "✅" if statuses[j] else "❌"
        final.append(f"{icon}  {step:<32} {mark}")

    final.append("")
    final.append(_progress_bar(100))
    final.append("")

    if passed == len(SCAN_STEPS):
        final.append("✅ *All checks passed!*  _Your files are safe._")
    else:
        failed = len(SCAN_STEPS) - passed
        final.append(f"⚠️ *{failed} check(s) failed*  _({passed}/{len(SCAN_STEPS)} passed)_")

    await _safe_edit(msg, "\n".join(final))


# ────────────────────────────────────────────────────────────
# Deploy animation
# ────────────────────────────────────────────────────────────

async def deploy_animation(msg: Message, python_version: str = "3.12") -> None:
    phases = [
        (0,   "🐳", "Pulling base image"),
        (20,  "🐳", "Building container"),
        (40,  "🐍", f"Configuring Python {python_version}"),
        (60,  "📦", "Installing dependencies"),
        (80,  "🔒", "Applying security policies"),
        (95,  "🚀", "Starting services"),
        (100, "✅", "Container is live!"),
    ]

    for tick, (pct, icon, label) in enumerate(phases):
        spin = _spinner(tick * 2)
        bar  = _progress_bar(pct)
        done = pct == 100

        frame = (
            f"{'✅' if done else '🐳'} *Deploying project*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"\n"
            f"{bar}\n"
            f"\n"
            f"{icon}  _{label}_\n"
            f"{'' if done else f'`{spin}` _Please wait…_'}"
        )
        await _safe_edit(msg, frame.strip())
        await asyncio.sleep(0.5)

    await asyncio.sleep(0.2)


# ────────────────────────────────────────────────────────────
# Package install animation
# ────────────────────────────────────────────────────────────

async def install_progress(msg: Message, packages: List[str]) -> None:
    statuses: List[str] = ["⬜"] * len(packages)

    for tick, i in enumerate(range(len(packages))):
        spin        = _spinner(tick * 3)
        statuses[i] = f"`{spin}`"

        pct  = round((i / len(packages)) * 100)
        rows = "\n".join(
            f"  {'📦' if j == i else ('✅' if st == '✅' else '·')} "
            f"`{pkg:<30}` {st}"
            for j, (pkg, st) in enumerate(zip(packages, statuses))
        )
        frame = (
            f"📦 *Installing packages*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"\n"
            f"{_progress_bar(pct)}\n"
            f"\n"
            f"{rows}"
        )
        await _safe_edit(msg, frame)
        await asyncio.sleep(0.4)
        statuses[i] = "✅"

    rows  = "\n".join(f"  ✅ `{pkg:<30}` ✅" for pkg in packages)
    frame = (
        f"📦 *All packages installed!*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"{_progress_bar(100)}\n"
        f"\n"
        f"{rows}\n"
        f"\n"
        f"🚀 _Ready to run!_"
    )
    await _safe_edit(msg, frame)


# ────────────────────────────────────────────────────────────
# Deletion animation
# ────────────────────────────────────────────────────────────

async def delete_animation(msg: Message) -> None:
    steps = [
        ("🛑", "Stopping container"),
        ("🗂️",  "Removing project files"),
        ("📋", "Clearing error logs"),
        ("🗄️",  "Cleaning database records"),
    ]

    completed: List[str] = []

    for tick, (icon, label) in enumerate(steps):
        for sub in range(4):
            spin   = _spinner(tick * 10 + sub)
            pulse  = _pulse(tick + sub)
            rows   = "\n".join(completed)
            active = f"{icon}  _{label}_  `{spin}`"
            frame  = (
                f"🗑️ *Deleting project*  `{pulse}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"\n"
                f"{rows + chr(10) if rows else ''}"
                f"{active}"
            )
            await _safe_edit(msg, frame.strip())
            await asyncio.sleep(0.15)

        completed.append(f"{icon}  {label:<28} ✅")

    summary = "\n".join(completed)
    final   = (
        f"🗑️ *Deletion complete*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"{summary}\n"
        f"\n"
        f"✅ _Project removed successfully._"
    )
    await _safe_edit(msg, final)


# ────────────────────────────────────────────────────────────
# Generic "thinking" spinner
# ────────────────────────────────────────────────────────────

async def thinking_animation(
    msg: Message,
    label: str = "Processing",
    ticks: int = 8,
    delay: float = 0.25,
) -> None:
    for t in range(ticks):
        spin  = _spinner(t)
        dots  = _dots(t)
        frame = (
            f"⚙️ *{label}{dots}*\n"
            f"\n"
            f"`{spin}` _Please wait…_"
        )
        await _safe_edit(msg, frame)
        await asyncio.sleep(delay)
