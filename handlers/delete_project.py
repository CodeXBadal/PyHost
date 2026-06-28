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
    """First confirmation step before deletion.

    FIX for BUG-035: previously this handler skipped the ownership check
    (only delete_confirmed verified it), which leaked a project's name
    to any user who guessed or learned its project_id.  We now refuse to
    render the confirmation prompt for non-owners and respond with a
    generic “not found” alert so the existence of the id is not
    confirmed either.
    """
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("delete_", "", 1)
    proj = await get_project(pid)
    if proj is None or proj["user_id"] != update.effective_user.id:
        # Same response for missing vs. not-owned to avoid disclosure.
        await q.answer("⛔ Not your project.", show_alert=True)
        return
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

    # SECURITY: verify the project belongs to the requesting user before
    # allowing deletion (a crafted delyes_<id> callback must not delete
    # someone else's project).
    if proj["user_id"] != update.effective_user.id:
        await q.answer("⛔ Not your project.", show_alert=True)
        return

    status_msg = await q.message.edit_text("🗑️ Deleting project...")
    try:
        await docker_manager.delete_container(
            pid, user_id=proj["user_id"], proj_name=proj["name"],
        )
    except Exception:
        pass
    try:
        clear_project_dir(pid, user_id=proj["user_id"], name=proj["name"])
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
