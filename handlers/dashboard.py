"""Project dashboard (RAM / CPU / Uptime / Requests / Crashes)."""
from __future__ import annotations

import re

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import PLAN_LIMITS
from database.models import get_project, get_or_create_user
from utils.helpers import progress_bar, human_uptime
from utils.keyboards import back_to_panel_keyboard
from utils.messages import DASHBOARD_MSG, NOT_FOUND
from core.docker_manager import docker_manager
from handlers.auth import require_member


@require_member
async def dashboard_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("dash_", "", 1)
    proj = await get_project(pid)
    if proj is None:
        await q.message.reply_text(NOT_FOUND); return

    user = await get_or_create_user(proj["user_id"], None)
    limits = PLAN_LIMITS.get(user.get("plan", "free"), PLAN_LIMITS["free"])
    running = (proj["status"] == "running")
    stats = await docker_manager.get_stats(pid) if running else {
        "ram_mb": 0, "cpu_percent": 0, "uptime_seconds": 0,
    }
    ram_pct = (stats["ram_mb"] / limits["ram_mb"] * 100) if limits["ram_mb"] else 0
    cpu_pct = stats["cpu_percent"]

    text = DASHBOARD_MSG.format(
        name=proj["name"],
        status_emoji="🟢" if running else "🔴",
        status="Running" if running else proj["status"].title(),
        uptime=human_uptime(stats["uptime_seconds"]),
        ram_mb=f"{stats['ram_mb']:.0f}",
        ram_limit=int(limits["ram_mb"]),
        ram_bar=progress_bar(ram_pct),
        ram_pct=int(ram_pct),
        cpu_pct=int(cpu_pct),
        cpu_limit=int(limits["cpu"] * 100),
        cpu_bar=progress_bar(cpu_pct),
        requests="—",
        crashes_today=proj.get("crash_count_today", 0),
        restarts_today=proj.get("crash_count_today", 0),
    )
    await q.message.edit_text(text, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=back_to_panel_keyboard(pid))
