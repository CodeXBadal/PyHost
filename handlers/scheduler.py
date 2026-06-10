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
    proj = await get_project(pid)
    if proj is None:
        await q.message.reply_text(NOT_FOUND); return
    sch = await list_schedules(pid)
    await q.message.edit_text(
        SCHED_MENU.format(name=proj["name"], list=_format_list(sch)),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=scheduler_menu_keyboard(pid, has_schedules=bool(sch)),
    )


@require_member
async def sched_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("schadd_", "", 1)
    context.user_data["sched_pid"] = pid
    await q.message.edit_text("Choose schedule type:",
                              reply_markup=scheduler_action_keyboard(pid))
    return SCHED_ACTION_PICK


@require_member
async def sched_pick_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    m = re.match(r"^schact_([0-9a-f]{12})_(restart|clearlogs|stats)$", q.data)
    if not m:
        return ConversationHandler.END
    pid, action = m.group(1), m.group(2)
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
        entry_points=[CallbackQueryHandler(sched_add, pattern=r"^schadd_[0-9a-f]{12}$")],
        states={
            SCHED_ACTION_PICK: [
                CallbackQueryHandler(sched_pick_action, pattern=r"^schact_[0-9a-f]{12}_(restart|clearlogs|stats)$"),
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
