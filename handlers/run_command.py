"""Edit-run-command flow."""
from __future__ import annotations

import re

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes, ConversationHandler,
    CallbackQueryHandler, MessageHandler, CommandHandler, filters,
)

from database.models import get_project, update_project
from utils.keyboards import cancel_keyboard, back_to_panel_keyboard
from utils.messages import RUNCMD_PROMPT, RUNCMD_UPDATED, RUNCMD_REJECTED, NOT_FOUND
from core.security import validate_run_command
from handlers.auth import require_member

RUN_CMD_INPUT = 100


@require_member
async def runcmd_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("runcmd_", "", 1)
    proj = await get_project(pid)
    if proj is None:
        await q.message.reply_text(NOT_FOUND); return ConversationHandler.END
    context.user_data["runcmd_pid"] = pid
    await q.message.edit_text(
        RUNCMD_PROMPT.format(name=proj["name"], current=proj["run_command"]),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=cancel_keyboard(),
    )
    return RUN_CMD_INPUT


async def runcmd_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pid = context.user_data.pop("runcmd_pid", None)
    if not pid:
        return ConversationHandler.END
    cmd = (update.message.text or "").strip()
    ok, reason = validate_run_command(cmd)
    if not ok:
        await update.message.reply_text(RUNCMD_REJECTED.format(cmd=reason),
                                        parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END
    await update_project(pid, {"run_command": cmd})
    await update.message.reply_text(
        RUNCMD_UPDATED.format(cmd=cmd),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_to_panel_keyboard(pid),
    )
    return ConversationHandler.END


async def runcmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("runcmd_pid", None)
    q = update.callback_query
    if q is not None:
        await q.answer()
        try:
            await q.message.edit_text("❌ Cancelled.")
        except Exception:
            pass
    return ConversationHandler.END


def build_runcmd_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(runcmd_entry, pattern=r"^runcmd_[0-9a-f]{12}$")],
        states={RUN_CMD_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, runcmd_save)]},
        fallbacks=[
            CommandHandler("cancel", runcmd_cancel),
            CallbackQueryHandler(runcmd_cancel, pattern=r"^cancel_flow$"),
        ],
        per_chat=True, allow_reentry=True, name="runcmd",
    )
