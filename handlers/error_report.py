"""
Manual error-report viewing handlers (the AUTO-send happens from core.error_logger
during a crash). This module provides a /errors command for inspection.
"""
from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database.models import recent_crashes, get_project
from utils.helpers import fmt_time
from utils.keyboards import back_to_panel_keyboard
from handlers.auth import require_member


@require_member
async def errors_for_project(update: Update, context: ContextTypes.DEFAULT_TYPE,
                             project_id: str) -> None:
    proj = await get_project(project_id)
    if proj is None:
        await update.effective_chat.send_message("Project not found."); return
    crashes = await recent_crashes(project_id, days=7)
    if not crashes:
        await update.effective_chat.send_message(
            "✅ No crashes in the last 7 days for this project.",
            reply_markup=back_to_panel_keyboard(project_id),
        )
        return
    lines = [f"💥 *Recent crashes — {proj['name']}*", ""]
    for c in crashes[:10]:
        lines.append(f"• {fmt_time(c['timestamp'])} — `{c.get('error_type','Error')}` "
                     f"(restart #{c.get('restart_attempt',0)})")
    await update.effective_chat.send_message("\n".join(lines),
                                             parse_mode=ParseMode.MARKDOWN,
                                             reply_markup=back_to_panel_keyboard(project_id))
