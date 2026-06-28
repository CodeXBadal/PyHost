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
from core.process_manager import process_manager as docker_manager
from handlers.auth import require_member

_OWNERSHIP_ERR = "⛔ Not your project."


async def _get_owned_project(update: Update, pid: str):
    proj = await get_project(pid)
    if proj is None:
        await update.callback_query.message.reply_text(NOT_FOUND)
        return None
    if proj["user_id"] != update.effective_user.id:
        await update.callback_query.answer(_OWNERSHIP_ERR, show_alert=True)
        return None
    return proj


@require_member
async def dashboard_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("dash_", "", 1)
    proj = await _get_owned_project(update, pid)
    if proj is None:
        return

    user = await get_or_create_user(proj["user_id"], None)
    limits = PLAN_LIMITS.get(user.get("plan", "free"), PLAN_LIMITS["free"])
    running = (proj["status"] == "running")
    # FIX for BUG-002 / BUG-010: pass user_id and proj_name so the process
    # manager resolves the new-layout directory projects/<user_id>/<name>/.
    # Without these, get_stats fell back to projects/<project_id>/ which
    # never exists for committed projects → always returned zeros.
    if running:
        stats = await docker_manager.get_stats(
            pid, user_id=proj["user_id"], proj_name=proj["name"],
        )
    else:
        stats = {"ram_mb": 0, "cpu_percent": 0, "uptime_seconds": 0}
    ram_pct = (stats["ram_mb"] / limits["ram_mb"] * 100) if limits["ram_mb"] else 0
    cpu_pct = stats["cpu_percent"]

    # FIX for BUG-025: restarts_today and crashes_today are now distinct
    # fields.  Previously both were filled with crash_count_today, so the
    # dashboard always showed the same value for both.  restart_count_today
    # is maintained separately by the project panel (on Restart button).
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
        restarts_today=proj.get("restart_count_today", 0),
    )
    await q.message.edit_text(text, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=back_to_panel_keyboard(pid))
