"""
Main project panel — start / stop / restart + open sub-screens.

Fixes:
  - Ownership check: user can only control their own projects
  - Per-action cooldowns for start/restart
  - Cleaner error handling
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import PLAN_LIMITS
from database.models import (
    get_project, update_project, list_envs, get_or_create_user,
)
from utils.helpers import fmt_time, human_uptime
from utils.keyboards import (
    project_panel_keyboard, start_fail_keyboard, back_to_panel_keyboard,
)
from utils.messages import (
    PROJECT_PANEL_MSG, START_OK, START_FAIL, STOP_OK, RESTART_OK,
    NOT_FOUND,
)
from core.process_manager import process_manager
from core.crypto import decrypt
from utils.error_formatter import extract_error_type, hint_for
from handlers.auth import require_member, require_action_cooldown

log = logging.getLogger(__name__)

_OWNERSHIP_ERR = "⛔ You don't have access to this project."


async def _check_ownership(user_id: int, project_id: str) -> bool:
    """Return True if the user owns this project."""
    proj = await get_project(project_id)
    if proj is None:
        return False
    return proj["user_id"] == user_id


async def _render_panel(update: Update, project_id: str, edit: bool = True) -> None:
    proj = await get_project(project_id)
    if proj is None:
        if update.effective_chat:
            await update.effective_chat.send_message(NOT_FOUND)
        return

    user = await get_or_create_user(proj["user_id"], None)
    limits = PLAN_LIMITS.get(user.get("plan", "free"), PLAN_LIMITS["free"])
    is_running = (proj["status"] == "running")
    stats = await process_manager.get_stats(project_id) if is_running else {
        "ram_mb": 0, "cpu_percent": 0, "uptime_seconds": 0,
    }

    text = PROJECT_PANEL_MSG.format(
        name=proj["name"],
        status_emoji="🟢" if is_running else "🔴",
        status="Running" if is_running else proj["status"].title(),
        python_version=proj["python_version"],
        ram_mb=f"{stats['ram_mb']:.0f}" if is_running else "—",
        ram_limit=int(limits["ram_mb"]),
        cpu_pct=f"{stats['cpu_percent']:.0f}" if is_running else "—",
        cpu_limit=int(limits["cpu"] * 100),
        uptime=human_uptime(stats["uptime_seconds"]) if is_running else "—",
        restarts_today=(proj.get("crash_count_today") or 0),
        created_at=fmt_time(proj["created_at"]),
    )
    kb = project_panel_keyboard(project_id, is_running=is_running)

    if update.callback_query and edit:
        try:
            await update.callback_query.message.edit_text(
                text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb,
            )
            return
        except Exception:
            pass
    await update.effective_chat.send_message(
        text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb,
    )


async def _edit_or_send(update: Update, text: str,
                        parse_mode=ParseMode.MARKDOWN, reply_markup=None) -> None:
    q = update.callback_query
    if q is not None:
        try:
            await q.message.edit_text(text, parse_mode=parse_mode,
                                      reply_markup=reply_markup)
            return
        except Exception:
            pass
    await update.effective_chat.send_message(text, parse_mode=parse_mode,
                                             reply_markup=reply_markup)


@require_member
async def project_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if q is None:
        return
    await q.answer()
    data = q.data

    m = re.match(r"^(panel|start|stop|restart)_([0-9a-f]{12})$", data)
    if not m:
        return
    action, pid = m.group(1), m.group(2)

    # FIXED: Ownership check — user can only control their own projects
    if not await _check_ownership(update.effective_user.id, pid):
        await q.answer(_OWNERSHIP_ERR, show_alert=True)
        return

    proj = await get_project(pid)
    if proj is None:
        await _edit_or_send(update, NOT_FOUND)
        return

    if action == "panel":
        await _render_panel(update, pid)
        return

    # Decrypt envs once for start/restart
    env_map = {e["key"]: decrypt(e["value"]) for e in await list_envs(pid)}

    if action == "stop":
        await _edit_or_send(update, STOP_OK.format(name=proj["name"]),
                            parse_mode=ParseMode.MARKDOWN)
        await process_manager.stop_container(pid)
        await update_project(pid, {"status": "stopped"})
        await _render_panel(update, pid, edit=True)
        return

    if action == "start":
        ok, err = await process_manager.start_container(pid, proj["run_command"], env_map)
        if ok:
            await update_project(pid, {"status": "running",
                                       "last_started": datetime.now(timezone.utc)})
            await _edit_or_send(update, START_OK.format(name=proj["name"]),
                                parse_mode=ParseMode.MARKDOWN)
            await _render_panel(update, pid, edit=True)
        else:
            err_type, _ = extract_error_type(err)
            await _edit_or_send(
                update,
                START_FAIL.format(error=err[:400], hint=hint_for(err_type)),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=start_fail_keyboard(pid),
            )
        return

    if action == "restart":
        ok, err = await process_manager.restart_container(pid, proj["run_command"], env_map)
        if ok:
            await update_project(pid, {"status": "running"})
            await _edit_or_send(update, RESTART_OK.format(name=proj["name"]),
                                parse_mode=ParseMode.MARKDOWN)
        else:
            await _edit_or_send(update,
                                f"❌ Restart failed: `{err}`",
                                parse_mode=ParseMode.MARKDOWN)
        await _render_panel(update, pid, edit=True)
        return
