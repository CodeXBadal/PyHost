"""Webhook / public URL management (Premium)."""
from __future__ import annotations

import re

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes, ConversationHandler,
    CallbackQueryHandler, MessageHandler, CommandHandler, filters,
)

from database.models import get_project, get_or_create_user, update_project
from utils.keyboards import webhook_keyboard, cancel_keyboard, back_to_panel_keyboard
from utils.messages import WEBHOOK_FREE, WEBHOOK_PREMIUM, WEBHOOK_PORT_PROMPT, WEBHOOK_PORT_SET, NOT_FOUND
from core.webhook_proxy import configure_proxy, public_url
from handlers.auth import require_member

WEBHOOK_PORT_INPUT = 400


@require_member
async def webhook_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("webhook_", "", 1)
    proj = await get_project(pid)
    if proj is None:
        await q.message.reply_text(NOT_FOUND); return
    user = await get_or_create_user(proj["user_id"], None)
    is_premium = user.get("plan") == "premium"
    if not is_premium:
        await q.message.edit_text(WEBHOOK_FREE, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=webhook_keyboard(pid, False))
        return
    url = proj.get("public_url") or public_url(proj["name"])
    port = proj.get("port") or "—"
    await q.message.edit_text(
        WEBHOOK_PREMIUM.format(name=proj["name"], url=url, port=port),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=webhook_keyboard(pid, True),
    )


@require_member
async def webhook_port_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("whport_", "", 1)
    context.user_data["wh_pid"] = pid
    await q.message.edit_text(WEBHOOK_PORT_PROMPT, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=cancel_keyboard())
    return WEBHOOK_PORT_INPUT


async def webhook_port_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pid = context.user_data.pop("wh_pid", None)
    if not pid:
        return ConversationHandler.END
    text = (update.message.text or "").strip()
    if not text.isdigit() or not (1 <= int(text) <= 65535):
        await update.message.reply_text("❌ Invalid port.")
        return ConversationHandler.END
    port = int(text)
    proj = await get_project(pid)
    if proj is None:
        return ConversationHandler.END
    ok, info = await configure_proxy(proj["name"], pid, port)
    url = info if ok else public_url(proj["name"])
    await update_project(pid, {"port": port, "public_url": url})
    await update.message.reply_text(
        WEBHOOK_PORT_SET.format(port=port, url=url),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_to_panel_keyboard(pid),
    )
    return ConversationHandler.END


@require_member
async def webhook_regen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer("Regenerated.")
    pid = q.data.replace("whregen_", "", 1)
    proj = await get_project(pid)
    if proj is None:
        return
    url = public_url(proj["name"])
    await update_project(pid, {"public_url": url})
    await q.message.reply_text(f"🔗 New URL:\n`{url}`",
                               parse_mode=ParseMode.MARKDOWN,
                               reply_markup=back_to_panel_keyboard(pid))


async def webhook_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("wh_pid", None)
    q = update.callback_query
    if q:
        await q.answer()
        try: await q.message.edit_text("❌ Cancelled.")
        except Exception: pass
    return ConversationHandler.END


def build_webhook_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(webhook_port_entry, pattern=r"^whport_[0-9a-f]{12}$")],
        states={
            WEBHOOK_PORT_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, webhook_port_save),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", webhook_cancel),
            CallbackQueryHandler(webhook_cancel, pattern=r"^cancel_flow$"),
        ],
        per_chat=True, allow_reentry=True, name="webhook",
    )
