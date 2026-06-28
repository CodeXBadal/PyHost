"""Per-project schedule management (auto restart / clear logs / daily stats)."""
from __future__ import annotations

import re

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes, ConversationHandler,
    CallbackQueryHandler, MessageHandler, CommandHandler, filters,
)

from database.models import (
    get_project, list_schedules, add_schedule, delete_schedule,
)
from utils.keyboards import (
    scheduler_menu_keyboard, scheduler_action_keyboard,
    back_to_panel_keyboard, cancel_keyboard,
)
from utils.messages import SCHED_MENU, SCHED_ADD_TIME, SCHED_ADDED, NOT_FOUND
from handlers.auth import require_member

SCHED_ACTION_PICK, SCHED_TIME_INPUT = range(300, 302)
_OWNERSHIP_ERR = "⛔ Not your project."


async def _get_owned_project(update: Update, pid: str):
    proj = await get_project(pid)
    if proj is None:
        if update.callback_query is not None:
            await update.callback_query.message.reply_text(NOT_FOUND)
        else:
            await update.message.reply_text(NOT_FOUND)
        return None
    if proj["user_id"] != update.effective_user.id:
        if update.callback_query is not None:
            await update.callback_query.answer(_OWNERSHIP_ERR, show_alert=True)
        else:
            await update.message.reply_text(_OWNERSHIP_ERR)
        return None
    return proj


async def _get_owned_schedule(update: Update, schedule_id: str):
    from database.connection import db
    sched = await db.schedules.find_one({"schedule_id": schedule_id})
    if not sched:
        if update.callback_query is not None:
            await update.callback_query.message.reply_text("Schedule not found.")
        else:
            await update.message.reply_text("Schedule not found.")
        return None
    proj = await _get_owned_project(update, sched["project_id"])
    if proj is None:
        return None
    return sched

ACTION_LABEL = {
    "restart":   "🔄 Auto Restart",
    "clearlogs": "🧹 Clear Logs",
    "stats":     "📊 Daily Stats Report",
}


def _format_list(schedules):
    if not schedules:
        return "_(none)_"
    out = []
    for s in schedules:
        label = ACTION_LABEL.get(s["action"], s["action"])
        out.append(f"• {label} — `{s['cron_expression']}`"
                   + (" ✅" if s["is_active"] else " ⏸"))
    return "\n".join(out)


@require_member
async def sched_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("sched_", "", 1)
    proj = await _get_owned_project(update, pid)
    if proj is None:
        return
    sch = await list_schedules(pid)
    await q.message.edit_text(
        SCHED_MENU.format(name=proj["name"], list=_format_list(sch)),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=scheduler_menu_keyboard(pid, has_schedules=bool(sch)),
    )


async def sched_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for the scheduler ConversationHandler.

    FIX for BUG-020: we no longer apply @require_member directly because
    the decorator returns ``None`` when a user is banned / rate-limited,
    which PTB's ConversationHandler treats ambiguously (a warning is
    logged and the flow silently terminates).  Instead we inline the
    membership/ban/rate-limit checks here and explicitly return
    ConversationHandler.END whenever they fail, so the user gets a clear
    cancellation rather than a silent drop.
    """
    from handlers.auth import _is_channel_member, _send_join_prompt
    from config import FORCE_JOIN_CHANNEL
    from database.models import get_or_create_user
    from database.redis_client import redis_client
    from utils.messages import RATE_LIMITED_MSG

    user = update.effective_user
    if user is not None:
        u = await get_or_create_user(user.id, user.username)
        if u.get("is_banned"):
            q = update.callback_query
            if q:
                await q.answer("🚫 You are banned from this bot.", show_alert=True)
            return ConversationHandler.END
        try:
            if await redis_client.is_rate_limited(user.id):
                ttl = await redis_client.rate_limit_ttl(user.id)
                q = update.callback_query
                if q:
                    await q.answer(RATE_LIMITED_MSG.format(seconds=ttl), show_alert=True)
                return ConversationHandler.END
        except Exception:
            pass
        if FORCE_JOIN_CHANNEL and not await _is_channel_member(context, user.id):
            await _send_join_prompt(update)
            return ConversationHandler.END

    q = update.callback_query
    await q.answer()
    pid = q.data.replace("schadd_", "", 1)
    proj = await _get_owned_project(update, pid)
    if proj is None:
        return ConversationHandler.END
    context.user_data["sched_pid"] = pid
    await q.message.edit_text("Choose schedule type:",
                              reply_markup=scheduler_action_keyboard(pid))
    return SCHED_ACTION_PICK


@require_member
async def sched_pick_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    m = re.match(r"^schact_([0-9a-f]{32})_(restart|clearlogs|stats)$", q.data)
    if not m:
        return ConversationHandler.END
    pid, action = m.group(1), m.group(2)
    proj = await _get_owned_project(update, pid)
    if proj is None:
        return ConversationHandler.END
    context.user_data["sched_pid"] = pid
    context.user_data["sched_action"] = action
    await q.message.edit_text(SCHED_ADD_TIME, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=cancel_keyboard())
    return SCHED_TIME_INPUT


async def sched_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pid    = context.user_data.pop("sched_pid", None)
    action = context.user_data.pop("sched_action", None)
    if not pid or not action:
        return ConversationHandler.END
    proj = await _get_owned_project(update, pid)
    if proj is None:
        return ConversationHandler.END
    text = (update.message.text or "").strip()
    if not re.match(r"^\d{1,2}:\d{2}$", text):
        await update.message.reply_text("❌ Invalid time. Use 24h format like `03:00`.")
        return ConversationHandler.END
    h, m = text.split(":")
    cron = f"{int(m)} {int(h)} * * *"
    await add_schedule(pid, action, cron)
    await update.message.reply_text(
        SCHED_ADDED.format(action=ACTION_LABEL.get(action, action), time=text),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_to_panel_keyboard(pid),
    )
    return ConversationHandler.END


@require_member
async def sched_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("schrm_", "", 1)
    proj = await _get_owned_project(update, pid)
    if proj is None:
        return
    sch = await list_schedules(pid)
    if not sch:
        await q.message.edit_text("No schedules to remove.",
                                  reply_markup=back_to_panel_keyboard(pid))
        return
    from utils.keyboards import _btn, _markup
    rows = []
    for s in sch:
        label = f"❌ {ACTION_LABEL.get(s['action'], s['action'])} ({s['cron_expression']})"
        rows.append([_btn(label, f"schdel_{s['schedule_id']}")])
    rows.append([_btn("🔙 Back", f"sched_{pid}")])
    await q.message.edit_text("Pick one to delete:", reply_markup=_markup(rows))


@require_member
async def sched_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer("Deleted.")
    sid = q.data.replace("schdel_", "", 1)
    sched = await _get_owned_schedule(update, sid)
    if not sched:
        return
    await delete_schedule(sid)
    await q.message.edit_text("✅ Schedule removed.")


async def sched_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("sched_pid", None)
    context.user_data.pop("sched_action", None)
    q = update.callback_query
    if q:
        await q.answer()
        try: await q.message.edit_text("❌ Cancelled.")
        except Exception: pass
    return ConversationHandler.END


def build_scheduler_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(sched_add, pattern=r"^schadd_[0-9a-f]{32}$")],
        states={
            SCHED_ACTION_PICK: [
                CallbackQueryHandler(sched_pick_action, pattern=r"^schact_[0-9a-f]{32}_(restart|clearlogs|stats)$"),
            ],
            SCHED_TIME_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, sched_save),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", sched_cancel),
            CallbackQueryHandler(sched_cancel, pattern=r"^cancel_flow$"),
        ],
        per_chat=True, allow_reentry=True, name="scheduler",
    )
