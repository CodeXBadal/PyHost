"""Logs viewer + downloader."""
from __future__ import annotations

import os
import re
import tempfile

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database.models import get_project
from utils.helpers import truncate, human_size
from utils.keyboards import logs_keyboard, back_to_panel_keyboard
from utils.messages import LOGS_HEAD, LOG_SENT, NOT_FOUND
from core.docker_manager import docker_manager
from handlers.auth import require_member


@require_member
async def logs_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("logs_", "", 1)
    proj = await get_project(pid)
    if proj is None:
        await q.message.reply_text(NOT_FOUND); return
    tail = await docker_manager.get_logs(pid, lines=40)
    tail = truncate(tail, 2500, tail=True) or "(empty)"
    await q.message.edit_text(
        LOGS_HEAD.format(name=proj["name"], tail=tail),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=logs_keyboard(pid),
    )


@require_member
async def logs_download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer("Preparing file...")
    m = re.match(r"^logd_([0-9a-f]{12})_(\d+|full|err)$", q.data)
    if not m:
        return
    pid, kind = m.group(1), m.group(2)
    proj = await get_project(pid)
    if proj is None:
        return

    errors_only = (kind == "err")
    if kind == "full":
        lines = 99999
    elif kind == "err":
        lines = 99999
    else:
        lines = int(kind)

    text = await docker_manager.get_logs(pid, lines=lines, errors_only=errors_only)
    if not text:
        text = "(no log data)"

    suffix = "-errors" if errors_only else ""
    filename = f"{proj['name']}-logs{suffix}.txt"
    tmp = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                      suffix=".txt", delete=False)
    tmp.write(text); tmp.close()
    size = os.path.getsize(tmp.name)

    with open(tmp.name, "rb") as fh:
        await q.message.reply_document(
            document=fh, filename=filename,
            caption=LOG_SENT.format(filename=filename,
                                    lines=text.count("\n") + 1,
                                    size=human_size(size)),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_to_panel_keyboard(pid),
        )
    try:
        os.remove(tmp.name)
    except Exception:
        pass
