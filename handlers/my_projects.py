"""/myprojects — paginated list of the user's projects."""
from __future__ import annotations

import math

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import PLAN_LIMITS
from database.models import get_or_create_user, list_projects
from utils.keyboards import my_projects_keyboard, back_to_menu_keyboard
from utils.messages import MY_PROJECTS_HEAD, MY_PROJECTS_EMPTY
from handlers.auth import require_member

PER_PAGE = 5


def _slice_for_page(items, page: int):
    total = max(1, math.ceil(len(items) / PER_PAGE))
    page  = max(1, min(page, total))
    start = (page - 1) * PER_PAGE
    return items[start:start + PER_PAGE], page, total


@require_member
async def my_projects_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    u = await get_or_create_user(user.id, user.username)
    plan = u.get("plan", "free")
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
    projects = await list_projects(user.id)
    if not projects:
        await _send(update, MY_PROJECTS_EMPTY, kb=back_to_menu_keyboard())
        return

    page = 1
    page_items, page, total = _slice_for_page(projects, page)
    text = MY_PROJECTS_HEAD.format(plan=plan.upper(), used=len(projects),
                                   limit=int(limits["projects"]),
                                   page=page, total_pages=total)
    await _send(update, text,
                kb=my_projects_keyboard(page_items, page, total, per_page=PER_PAGE))


async def _send(update: Update, text: str, kb):
    target = update.callback_query.message if update.callback_query else update.effective_chat
    if update.callback_query:
        try:
            await target.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
            return
        except Exception:
            pass
    await update.effective_chat.send_message(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


@require_member
async def my_projects_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    page = int(q.data.replace("mp_page_", ""))
    user = update.effective_user
    u = await get_or_create_user(user.id, user.username)
    plan = u.get("plan", "free")
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
    projects = await list_projects(user.id)
    page_items, page, total = _slice_for_page(projects, page)
    text = MY_PROJECTS_HEAD.format(plan=plan.upper(), used=len(projects),
                                   limit=int(limits["projects"]),
                                   page=page, total_pages=total)
    await q.message.edit_text(text, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=my_projects_keyboard(page_items, page, total))
