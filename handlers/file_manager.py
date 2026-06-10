"""Browse + download project files."""
from __future__ import annotations

import os
import re

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database.models import get_project
from utils.helpers import human_size
from utils.keyboards import file_manager_keyboard, back_to_panel_keyboard
from utils.messages import FILE_MANAGER_HEAD, NOT_FOUND
from core.file_handler import list_tree, get_file_path
from handlers.auth import require_member


def _render(entries, current_rel: str):
    lines = []
    for e in entries[:30]:
        icon = "📁" if e["is_dir"] else "📄"
        if e["is_dir"]:
            lines.append(f"{icon} {e['name']}/")
        else:
            lines.append(f"{icon} {e['name']}  ({human_size(e['size'])})")
    return "\n".join(lines) or "_(empty folder)_"


@require_member
async def fm_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("files_", "", 1)
    proj = await get_project(pid)
    if proj is None:
        await q.message.reply_text(NOT_FOUND); return
    entries = list_tree(pid, "")
    head = FILE_MANAGER_HEAD.format(name=proj["name"], path="")
    text = head + "\n```\n" + _render(entries, "") + "\n```"
    await q.message.edit_text(text, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=file_manager_keyboard(pid, entries))


@require_member
async def fm_cd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    m = re.match(r"^fmcd_([0-9a-f]{12})_(.*)$", q.data)
    if not m:
        return
    pid, rel = m.group(1), m.group(2)
    proj = await get_project(pid)
    if proj is None:
        await q.message.reply_text(NOT_FOUND); return
    entries = list_tree(pid, rel)
    head = FILE_MANAGER_HEAD.format(name=proj["name"], path=rel)
    text = head + "\n```\n" + _render(entries, rel) + "\n```"
    try:
        await q.message.edit_text(text, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=file_manager_keyboard(pid, entries, rel))
    except Exception:
        pass


@require_member
async def fm_get(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer("Sending file...")
    m = re.match(r"^fmget_([0-9a-f]{12})_(.+)$", q.data)
    if not m:
        return
    pid, rel = m.group(1), m.group(2)
    path = get_file_path(pid, rel)
    if not path or not os.path.isfile(path):
        await q.message.reply_text("File not found."); return
    with open(path, "rb") as fh:
        await q.message.reply_document(
            document=fh, filename=os.path.basename(path),
            caption=f"📎 `{rel}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_to_panel_keyboard(pid),
        )
