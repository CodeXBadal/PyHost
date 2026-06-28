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
async def logs_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("logs_", "", 1)
    proj = await _get_owned_project(update, pid)
    if proj is None:
        return
    tail = await docker_manager.get_logs(
        pid, lines=40, user_id=proj["user_id"], proj_name=proj["name"],
    )
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
    m = re.match(r"^logd_([0-9a-f]{32})_(\d+|full|err)$", q.data)
    if not m:
        return
    pid, kind = m.group(1), m.group(2)
    proj = await _get_owned_project(update, pid)
    if proj is None:
        return

    errors_only = (kind == "err")
    if kind == "full":
        lines = 99999
    elif kind == "err":
        lines = 99999
    else:
        lines = int(kind)

    # FIX for BUG-003 / BUG-011: must forward user_id + proj_name so the
    # process manager resolves the new-layout log path
    # (projects/<user_id>/<name>/.pyhost.log) instead of the legacy
    # projects/<project_id>/ which never exists for committed projects.
    text = await docker_manager.get_logs(
        pid, lines=lines, errors_only=errors_only,
        user_id=proj["user_id"], proj_name=proj["name"],
    )
    if not text:
        text = "(no log data)"

    suffix = "-errors" if errors_only else ""
    filename = f"{proj['name']}-logs{suffix}.txt"
    tmp = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                      suffix=".txt", delete=False)
    tmp.write(text); tmp.close()
    # Restrict tmp file permissions to owner only (defence-in-depth on
    # multi-user hosts; log contents may contain stack-trace fragments).
    try:
        os.chmod(tmp.name, 0o600)
    except OSError:
        pass
    size = os.path.getsize(tmp.name)

    try:
        with open(tmp.name, "rb") as fh:
            await q.message.reply_document(
                document=fh, filename=filename,
                caption=LOG_SENT.format(filename=filename,
                                        lines=text.count("\n") + 1,
                                        size=human_size(size)),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=back_to_panel_keyboard(pid),
            )
    finally:
        try:
            os.remove(tmp.name)
        except Exception:
            pass
