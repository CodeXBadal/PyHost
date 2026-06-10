"""Install dependencies flow."""
from __future__ import annotations

import re

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database.models import get_project
from utils.animations import install_progress
from utils.keyboards import install_deps_keyboard, back_to_panel_keyboard
from utils.messages import DEPS_FOUND, DEPS_NO_FILE, NOT_FOUND
from core.file_handler import read_requirements
from core.dependency_installer import install_dependencies
from handlers.auth import require_member


@require_member
async def deps_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("deps_", "", 1)
    proj = await get_project(pid)
    if proj is None:
        await q.message.reply_text(NOT_FOUND); return

    pkgs = read_requirements(pid)
    if not pkgs:
        await q.message.edit_text(DEPS_NO_FILE, reply_markup=back_to_panel_keyboard(pid))
        return
    await q.message.edit_text(
        DEPS_FOUND.format(name=proj["name"],
                          packages="\n".join(pkgs),
                          count=len(pkgs)),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=install_deps_keyboard(pid),
    )


@require_member
async def deps_go(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("depsgo_", "", 1)
    proj = await get_project(pid)
    if proj is None:
        await q.message.reply_text(NOT_FOUND); return

    pkgs = read_requirements(pid)
    if not pkgs:
        await q.message.edit_text(DEPS_NO_FILE); return

    status = await q.message.edit_text("⏳ *Installing dependencies...*\n_This may take a few minutes._",
                                       parse_mode=ParseMode.MARKDOWN)
    await install_progress(status, pkgs)

    ok, output, _ = await install_dependencies(pid)
    if ok:
        await q.message.reply_text(
            f"🎉 *All {len(pkgs)} dependencies installed!*\nYou can now *Start* your project.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_to_panel_keyboard(pid),
        )
    else:
        # show tail of pip output for diagnostic help
        tail = (output or "")[-1500:]
        await q.message.reply_text(
            f"❌ Install failed.\n```\n{tail}\n```",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_to_panel_keyboard(pid),
        )
