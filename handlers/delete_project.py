"""Delete project (with double confirmation + cleanup animation)."""
from __future__ import annotations

import shutil

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database.models import get_project, delete_project
from utils.animations import delete_animation
from utils.keyboards import delete_confirm_keyboard, _btn, _markup
from utils.messages import DELETE_CONFIRM, DELETE_DONE, NOT_FOUND
from core.process_manager import process_manager as docker_manager
from core.file_handler import clear_project_dir
from handlers.auth import require_member


@require_member
async def delete_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("delete_", "", 1)
    proj = await get_project(pid)
    if proj is None:
        await q.message.reply_text(NOT_FOUND); return
    await q.message.edit_text(
        DELETE_CONFIRM.format(name=proj["name"]),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=delete_confirm_keyboard(pid),
    )


@require_member
async def delete_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer("Deleting...")
    pid = q.data.replace("delyes_", "", 1)
    proj = await get_project(pid)
    if proj is None:
        await q.message.reply_text(NOT_FOUND); return

    status_msg = await q.message.edit_text("🗑️ Deleting project...")
    try:
        await docker_manager.delete_container(pid)
    except Exception:
        pass
    try:
        clear_project_dir(pid)
    except Exception:
        pass
    await delete_project(pid)

    await delete_animation(status_msg)
    await status_msg.reply_text(
        DELETE_DONE, parse_mode=ParseMode.MARKDOWN,
        reply_markup=_markup([
            [_btn("🆕 Create New Project", "new_project", style="success"),
             _btn("🏠 Main Menu",          "main_menu")],
        ]),
    )
