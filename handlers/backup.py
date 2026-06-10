"""Backup & restore handlers."""
from __future__ import annotations

import os
import re

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database.models import (
    get_project, add_backup, list_backups, delete_backup,
)
from utils.helpers import human_size, fmt_time
from utils.keyboards import (
    backup_menu_keyboard, backup_list_keyboard, back_to_panel_keyboard,
    confirm_cancel_keyboard,
)
from utils.messages import (
    BACKUP_MENU, BACKUP_DONE, BACKUP_LIST_HEAD,
    BACKUP_RESTORE_WARN, BACKUP_RESTORE_DONE, NOT_FOUND,
)
from core.backup_manager import create_backup, restore_backup, delete_backup_file
from handlers.auth import require_member


@require_member
async def backup_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("backup_", "", 1)
    proj = await get_project(pid)
    if proj is None:
        await q.message.reply_text(NOT_FOUND); return
    await q.message.edit_text(BACKUP_MENU.format(name=proj["name"]),
                              parse_mode=ParseMode.MARKDOWN,
                              reply_markup=backup_menu_keyboard(pid))


@require_member
async def backup_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer("Creating backup...")
    pid = q.data.replace("bkcreate_", "", 1)
    proj = await get_project(pid)
    if proj is None:
        await q.message.reply_text(NOT_FOUND); return
    path, size = create_backup(pid, proj["name"])
    doc = await add_backup(pid, proj["user_id"], path, size)
    await q.message.reply_text(
        BACKUP_DONE.format(filename=os.path.basename(path), size=human_size(size)),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_to_panel_keyboard(pid),
    )


@require_member
async def backup_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("bklist_", "", 1)
    proj = await get_project(pid)
    backups = await list_backups(pid)
    if not backups:
        await q.message.edit_text("No backups yet.",
                                  reply_markup=back_to_panel_keyboard(pid))
        return
    lines = [BACKUP_LIST_HEAD.format(name=proj["name"])]
    for i, b in enumerate(backups[:10], 1):
        lines.append(f"{i}. `{os.path.basename(b['file_path'])}` — "
                     f"{human_size(b['size_bytes'])} ({fmt_time(b['created_at'])})")
    await q.message.edit_text("\n".join(lines),
                              parse_mode=ParseMode.MARKDOWN,
                              reply_markup=backup_list_keyboard(pid, backups))


@require_member
async def backup_download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer("Sending backup...")
    bid = q.data.replace("bkdl_", "", 1)
    backups = await list_backups_by_id(bid)
    if not backups:
        await q.message.reply_text("Backup not found."); return
    b = backups
    if not os.path.exists(b["file_path"]):
        await q.message.reply_text("Backup file is missing on disk."); return
    pid = b["project_id"]
    with open(b["file_path"], "rb") as fh:
        await q.message.reply_document(
            document=fh, filename=os.path.basename(b["file_path"]),
            caption=f"📦 Backup ({human_size(b['size_bytes'])})",
            reply_markup=back_to_panel_keyboard(pid),
        )


# helper because backups don't have a "find one" model fn
async def list_backups_by_id(bid: str):
    from database.connection import db
    return await db.backups.find_one({"backup_id": bid})


@require_member
async def backup_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer("Deleting...")
    bid = q.data.replace("bkrm_", "", 1)
    doc = await delete_backup(bid)
    if doc:
        delete_backup_file(doc["file_path"])
    pid = doc["project_id"] if doc else None
    if pid:
        await backup_list(update, context)
    else:
        await q.message.reply_text("Deleted.")


@require_member
async def backup_restore_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show backup list with restore action."""
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("bkrestore_", "", 1)
    backups = await list_backups(pid)
    if not backups:
        await q.message.edit_text("No backups to restore.",
                                  reply_markup=back_to_panel_keyboard(pid))
        return
    from utils.keyboards import _btn, _markup
    rows = []
    for b in backups[:10]:
        label = f"📦 {fmt_time(b['created_at'])} — {human_size(b['size_bytes'])}"
        rows.append([_btn(label, f"bkrok_{b['backup_id']}")])
    rows.append([_btn("❌ Cancel", f"backup_{pid}", style="danger")])
    await q.message.edit_text("Pick a backup to restore:", reply_markup=_markup(rows))


@require_member
async def backup_restore_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    bid = q.data.replace("bkrok_", "", 1)
    b = await list_backups_by_id(bid)
    if not b:
        await q.message.reply_text("Backup not found."); return
    context.user_data["restore_bid"] = bid
    await q.message.edit_text(BACKUP_RESTORE_WARN,
                              parse_mode=ParseMode.MARKDOWN,
                              reply_markup=confirm_cancel_keyboard(
                                  confirm_data=f"bkdo_{bid}",
                                  cancel_data=f"backup_{b['project_id']}",
                              ))


@require_member
async def backup_restore_do(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer("Restoring...")
    bid = q.data.replace("bkdo_", "", 1)
    b = await list_backups_by_id(bid)
    if not b:
        await q.message.reply_text("Backup not found."); return
    ok, err = restore_backup(b["project_id"], b["file_path"])
    if not ok:
        await q.message.reply_text(f"❌ {err}"); return
    await q.message.edit_text(BACKUP_RESTORE_DONE,
                              reply_markup=back_to_panel_keyboard(b["project_id"]))
