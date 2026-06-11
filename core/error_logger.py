"""
Real-time error / crash capture.

The function `on_container_crashed()` is the single entry point used by the
monitor: it gathers the container's tail, builds the formatted .txt report,
writes it under user_data/error_logs/<project_id>/, persists a crash_logs row
in MongoDB, and asks the Telegram-side helper to send the report to the user.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from telegram import Bot
from telegram.constants import ParseMode

from config import (
    AUTO_RESTART_MAX_ATTEMPTS, ERRLOG_DIR, PLAN_LIMITS,
)
from database.models import (
    get_project, log_crash, update_project, get_or_create_user,
)
from utils.error_formatter import build_report, write_report_file
from utils.keyboards import error_report_keyboard
from utils.messages import CRASH_NOTIFY
from utils.helpers import human_uptime
from .process_manager import process_manager as docker_manager

log = logging.getLogger(__name__)


async def collect_traceback(project_id: str, lines: int = 200) -> str:
    """Return the tail of the container log (best-effort)."""
    try:
        return await docker_manager.get_logs(project_id, lines=lines, errors_only=False)
    except Exception as exc:
        log.exception("collect_traceback: %s", exc)
        return ""


async def on_container_crashed(*, bot: Bot, project_id: str,
                               exit_code: int = 1,
                               restart_attempt: int = 0,
                               uptime_seconds: int = 0,
                               ram_mb: float = 0,
                               cpu_pct: float = 0) -> Optional[dict]:
    """Build crash report, store, notify user. Returns the crash document."""
    proj = await get_project(project_id)
    if proj is None:
        return None
    user_id = proj["user_id"]
    project_name = proj["name"]

    user = await get_or_create_user(user_id, None)
    plan_lim = PLAN_LIMITS.get(user.get("plan", "free"), PLAN_LIMITS["free"])

    traceback_text = await collect_traceback(project_id)
    report = build_report(
        project_name=project_name,
        exit_code=exit_code,
        restart_attempt=restart_attempt,
        max_restarts=AUTO_RESTART_MAX_ATTEMPTS,
        traceback_text=traceback_text,
        ram_mb=ram_mb,
        ram_limit_mb=plan_lim["ram_mb"],
        cpu_pct=cpu_pct,
        uptime_str=human_uptime(uptime_seconds),
    )

    # write txt file
    project_log_dir = os.path.join(ERRLOG_DIR, project_id)
    full_path = write_report_file(project_log_dir, report["filename"], report["body"])

    # persist crash row
    crash_doc = {
        "project_id":      project_id,
        "exit_code":       exit_code,
        "traceback":       traceback_text[-4000:],
        "error_type":      report["error_type"],
        "hint_shown":      report["hint"],
        "auto_restarted":  restart_attempt > 0,
        "notified_user":   True,
        "ram_at_crash":    ram_mb,
        "uptime_seconds":  uptime_seconds,
        "restart_attempt": restart_attempt,
    }
    await log_crash(crash_doc)
    await update_project(project_id, {
        "status":            "crashed",
        "last_error_at":     crash_doc.get("timestamp"),
        "crash_count_today": (proj.get("crash_count_today") or 0) + 1,
    })

    # send to user
    try:
        restart_status = ("Auto-restarted ✅"
                          if restart_attempt > 0 and restart_attempt < AUTO_RESTART_MAX_ATTEMPTS
                          else "Stopped — please fix and start manually")
        text = CRASH_NOTIFY.format(
            name=project_name,
            exit_code=exit_code,
            uptime=human_uptime(uptime_seconds),
            restart_status=restart_status,
            error_type=report["error_type"],
            error_line=report["error_line"].replace("`", "'")[:120],
        )
        await bot.send_message(
            chat_id=user_id, text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=error_report_keyboard(project_id),
        )
        with open(full_path, "rb") as fh:
            await bot.send_document(
                chat_id=user_id, document=fh,
                filename=report["filename"],
                caption=f"📎 Error report for `{project_name}`",
                parse_mode=ParseMode.MARKDOWN,
            )
    except Exception as exc:
        log.exception("Failed to notify user %s about crash: %s", user_id, exc)

    return crash_doc
