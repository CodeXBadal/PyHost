"""Admin panel — /admin command."""
from __future__ import annotations

import logging
import psutil
import re
from typing import Optional

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes, ConversationHandler,
    CommandHandler, CallbackQueryHandler, MessageHandler, filters,
)

from config import ADMIN_IDS
from database.models import (
    count_users, all_users, ban_user, set_user_plan,
    all_projects, all_recent_crashes,
)
from utils.helpers import fmt_time, human_size
from utils.keyboards import (
    admin_menu_keyboard, admin_broadcast_type_keyboard, back_to_menu_keyboard,
    _btn, _markup,
)
from utils.messages import ADMIN_PANEL, ADMIN_ONLY
from core.process_manager import process_manager as docker_manager

log = logging.getLogger(__name__)


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ────────────────────────────────────────────────────────────
# states
ADM_BCAST_TYPE, ADM_BCAST_TEXT, ADM_BCAST_IMAGE = range(500, 503)
ADM_UPGRADE_ID, ADM_UPGRADE_PLAN = range(510, 512)
ADM_BAN_ID, ADM_UNBAN_ID = range(520, 522)


# ────────────────────────────────────────────────────────────
# panel
# ────────────────────────────────────────────────────────────
async def _render_panel(update: Update) -> None:
    n_users = await count_users()
    projects = await all_projects()
    running = sum(1 for p in projects if p["status"] == "running")
    vmem = psutil.virtual_memory()
    text = ADMIN_PANEL.format(
        users=n_users, running=running,
        ram_used=f"{vmem.used/1024**3:.1f}",
        ram_total=f"{vmem.total/1024**3:.1f}",
        cpu_pct=f"{psutil.cpu_percent(interval=0.1):.0f}",
    )
    target = update.callback_query.message if update.callback_query else update.effective_chat
    if update.callback_query:
        try:
            await target.edit_text(text, parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=admin_menu_keyboard()); return
        except Exception: pass
    await update.effective_chat.send_message(text, parse_mode=ParseMode.MARKDOWN,
                                             reply_markup=admin_menu_keyboard())


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id):
        await update.effective_chat.send_message(ADMIN_ONLY); return
    await _render_panel(update)


async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    if not _is_admin(update.effective_user.id):
        await q.answer(ADMIN_ONLY, show_alert=True); return
    await _render_panel(update)


# ── users list ──────────────────────────────────────────────
async def adm_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    if not _is_admin(update.effective_user.id):
        return
    users = await all_users(limit=20)
    lines = ["👥 *Users (recent 20)*", ""]
    for u in users:
        ban = "🚫" if u.get("is_banned") else "✅"
        lines.append(f"{ban} `{u['user_id']}` @{u.get('username','—')} — *{u.get('plan','free')}* "
                     f"({u.get('projects_count',0)} apps)")
    await q.message.edit_text("\n".join(lines),
                              parse_mode=ParseMode.MARKDOWN,
                              reply_markup=_markup([[_btn("🔙 Back", "admin_panel")]]))


# ── server stats ────────────────────────────────────────────
async def adm_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    if not _is_admin(update.effective_user.id):
        return
    vmem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    text = (
        f"📊 *Server Stats*\n\n"
        f"CPU      : {psutil.cpu_percent(interval=0.5):.0f}%\n"
        f"RAM      : {vmem.used/1024**3:.1f} / {vmem.total/1024**3:.1f} GB\n"
        f"Disk     : {disk.used/1024**3:.1f} / {disk.total/1024**3:.1f} GB\n"
    )
    await q.message.edit_text(text, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=_markup([[_btn("🔙 Back", "admin_panel")]]))


# ── containers ──────────────────────────────────────────────
async def adm_containers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    if not _is_admin(update.effective_user.id):
        return
    conts = await docker_manager.list_pyhost_containers()
    if not conts:
        text = "🐳 No PyHost containers."
    else:
        lines = ["🐳 *All PyHost containers*", ""]
        for c in conts[:30]:
            lines.append(f"• `{c['id']}` `{c['name']}` — *{c['status']}*")
        text = "\n".join(lines)
    await q.message.edit_text(text, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=_markup([[_btn("🔙 Back", "admin_panel")]]))


async def adm_cleanup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer("Cleaning...")
    if not _is_admin(update.effective_user.id):
        return
    projects = await all_projects()
    valid = {p["project_id"] for p in projects}
    n = await docker_manager.cleanup_dead(valid)
    await q.message.edit_text(
        f"🧹 Cleaned `{n}` dead containers.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_markup([[_btn("🔙 Back", "admin_panel")]]),
    )


async def adm_errors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    if not _is_admin(update.effective_user.id):
        return
    crashes = await all_recent_crashes(hours=24)
    if not crashes:
        text = "✅ No crashes in the last 24h."
    else:
        lines = ["📋 *Crashes — last 24h*", ""]
        for c in crashes[:30]:
            lines.append(f"• `{c['project_id'][:8]}` — `{c.get('error_type','?')}`"
                         f" — {fmt_time(c['timestamp'])}")
        lines.append(f"\nTotal: *{len(crashes)}*")
        text = "\n".join(lines)
    await q.message.edit_text(text, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=_markup([[_btn("🔙 Back", "admin_panel")]]))


# ── ban / unban / upgrade ───────────────────────────────────
async def _ask_uid(q, prompt, ret_state):
    await q.message.edit_text(prompt, reply_markup=_markup([[_btn("❌ Cancel", "admin_panel")]]))
    return ret_state


async def adm_ban_entry(update, context):
    q = update.callback_query; await q.answer()
    if not _is_admin(update.effective_user.id): return ConversationHandler.END
    return await _ask_uid(q, "Send user_id to *BAN*:", ADM_BAN_ID)


async def adm_ban_save(update, context):
    try: uid = int(update.message.text.strip())
    except Exception:
        await update.message.reply_text("Invalid id."); return ConversationHandler.END
    await ban_user(uid, True)
    await update.message.reply_text(f"🚫 Banned `{uid}`.", parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


async def adm_unban_entry(update, context):
    q = update.callback_query; await q.answer()
    if not _is_admin(update.effective_user.id): return ConversationHandler.END
    return await _ask_uid(q, "Send user_id to *UNBAN*:", ADM_UNBAN_ID)


async def adm_unban_save(update, context):
    try: uid = int(update.message.text.strip())
    except Exception:
        await update.message.reply_text("Invalid id."); return ConversationHandler.END
    await ban_user(uid, False)
    await update.message.reply_text(f"✅ Unbanned `{uid}`.", parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


async def adm_upgrade_entry(update, context):
    q = update.callback_query; await q.answer()
    if not _is_admin(update.effective_user.id): return ConversationHandler.END
    return await _ask_uid(q, "Send user_id to upgrade:", ADM_UPGRADE_ID)


async def adm_upgrade_id(update, context):
    try: uid = int(update.message.text.strip())
    except Exception:
        await update.message.reply_text("Invalid id."); return ConversationHandler.END
    context.user_data["adm_uid"] = uid
    await update.message.reply_text("Send plan (`free` or `premium`):", parse_mode=ParseMode.MARKDOWN)
    return ADM_UPGRADE_PLAN


async def adm_upgrade_plan(update, context):
    uid = context.user_data.pop("adm_uid", None)
    plan = (update.message.text or "").strip().lower()
    if plan not in ("free", "premium"):
        await update.message.reply_text("Plan must be `free` or `premium`."); return ConversationHandler.END
    await set_user_plan(uid, plan)
    await update.message.reply_text(f"✅ `{uid}` is now *{plan}*.", parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END


# ── broadcast ───────────────────────────────────────────────
async def adm_broadcast_entry(update, context):
    q = update.callback_query; await q.answer()
    if not _is_admin(update.effective_user.id): return ConversationHandler.END
    await q.message.edit_text("📢 *Broadcast*", parse_mode=ParseMode.MARKDOWN,
                              reply_markup=admin_broadcast_type_keyboard())
    return ADM_BCAST_TYPE


async def adm_broadcast_type(update, context):
    q = update.callback_query; await q.answer()
    if q.data == "bcast_text":
        await q.message.edit_text("Send the broadcast *text* now:", parse_mode=ParseMode.MARKDOWN)
        return ADM_BCAST_TEXT
    if q.data == "bcast_image":
        await q.message.edit_text("Send the broadcast *image with caption* now:",
                                  parse_mode=ParseMode.MARKDOWN)
        return ADM_BCAST_IMAGE
    return ConversationHandler.END


async def _broadcast_send(context, send_fn) -> int:
    users = await all_users(limit=100000)
    sent = 0; failed = 0
    for u in users:
        try:
            await send_fn(u["user_id"])
            sent += 1
        except Exception:
            failed += 1
    return sent, failed


async def adm_broadcast_text(update, context):
    txt = update.message.text or ""
    async def send(uid):
        await context.bot.send_message(uid, txt, parse_mode=ParseMode.MARKDOWN)
    sent, failed = await _broadcast_send(context, send)
    await update.message.reply_text(f"📢 Sent: {sent} | Failed: {failed}")
    return ConversationHandler.END


async def adm_broadcast_image(update, context):
    if not update.message.photo:
        await update.message.reply_text("Send a photo with caption."); return ConversationHandler.END
    file_id = update.message.photo[-1].file_id
    caption = update.message.caption or ""
    async def send(uid):
        await context.bot.send_photo(uid, photo=file_id, caption=caption,
                                     parse_mode=ParseMode.MARKDOWN)
    sent, failed = await _broadcast_send(context, send)
    await update.message.reply_text(f"📢 Sent: {sent} | Failed: {failed}")
    return ConversationHandler.END


async def adm_cancel(update, context):
    if update.callback_query:
        await update.callback_query.answer()
        try: await update.callback_query.message.edit_text("❌ Cancelled.")
        except Exception: pass
    return ConversationHandler.END


def build_admin_handlers():
    """Return list of handlers to register from main.py."""
    broadcast = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_broadcast_entry, pattern=r"^adm_broadcast$")],
        states={
            ADM_BCAST_TYPE:  [CallbackQueryHandler(adm_broadcast_type, pattern=r"^bcast_(text|image)$")],
            ADM_BCAST_TEXT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_broadcast_text)],
            ADM_BCAST_IMAGE: [MessageHandler(filters.PHOTO, adm_broadcast_image)],
        },
        fallbacks=[CallbackQueryHandler(adm_cancel, pattern=r"^admin_panel$")],
        per_chat=True, allow_reentry=True, name="adm_broadcast",
    )
    upgrade = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_upgrade_entry, pattern=r"^adm_upgrade$")],
        states={
            ADM_UPGRADE_ID:   [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_upgrade_id)],
            ADM_UPGRADE_PLAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_upgrade_plan)],
        },
        fallbacks=[CallbackQueryHandler(adm_cancel, pattern=r"^admin_panel$")],
        per_chat=True, allow_reentry=True, name="adm_upgrade",
    )
    ban = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_ban_entry, pattern=r"^adm_ban$")],
        states={ADM_BAN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_ban_save)]},
        fallbacks=[CallbackQueryHandler(adm_cancel, pattern=r"^admin_panel$")],
        per_chat=True, allow_reentry=True, name="adm_ban",
    )
    unban = ConversationHandler(
        entry_points=[CallbackQueryHandler(adm_unban_entry, pattern=r"^adm_unban$")],
        states={ADM_UNBAN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_unban_save)]},
        fallbacks=[CallbackQueryHandler(adm_cancel, pattern=r"^admin_panel$")],
        per_chat=True, allow_reentry=True, name="adm_unban",
    )
    return [broadcast, upgrade, ban, unban]
