"""/start command — welcome banner + main menu."""
from __future__ import annotations

import logging
import os

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import PLAN_LIMITS, WELCOME_BANNER_PATH
from database.models import get_or_create_user, list_projects
from utils.keyboards import start_menu_keyboard, back_to_menu_keyboard
from utils.messages import (
    WELCOME_MSG, HELP_MSG, SUPPORT_MSG, UPGRADE_MSG,
)
from handlers.auth import require_member

log = logging.getLogger(__name__)


async def _send_start_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db_user = await get_or_create_user(user.id, user.username)
    plan = db_user.get("plan", "free")
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
    projects = await list_projects(user.id)

    text = WELCOME_MSG.format(
        plan=plan.upper(),
        apps_used=len(projects),
        apps_limit=int(limits["projects"]),
        ram_mb=int(limits["ram_mb"]),
    )

    kb = start_menu_keyboard()
    chat = update.effective_chat

    # photo if available, otherwise text
    if os.path.isfile(WELCOME_BANNER_PATH):
        try:
            with open(WELCOME_BANNER_PATH, "rb") as fh:
                await chat.send_photo(photo=fh, caption=text,
                                      parse_mode=ParseMode.MARKDOWN,
                                      reply_markup=kb)
            return
        except Exception as exc:
            log.debug("welcome photo failed, falling back to text: %s", exc)
    await chat.send_message(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


@require_member
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_start_card(update, context)


@require_member
async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return to the main menu.

    BUG-028: we explicitly delete the previous message (which may be a
    photo card from the welcome banner) before sending the fresh menu so
    the stale photo never lingers above the new text reply.
    """
    q = update.callback_query
    if q is None:
        return
    await q.answer()
    try:
        await q.message.delete()
    except Exception:
        pass
    await _send_start_card(update, context)


@require_member
async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    # Edit the existing message instead of sending a new one
    try:
        await q.message.edit_text(HELP_MSG, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=back_to_menu_keyboard())
    except Exception:
        await q.message.reply_text(HELP_MSG, parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=back_to_menu_keyboard())


@require_member
async def support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    # Edit the existing message instead of sending a new one
    try:
        await q.message.edit_text(SUPPORT_MSG, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=back_to_menu_keyboard())
    except Exception:
        await q.message.reply_text(SUPPORT_MSG, parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=back_to_menu_keyboard())


@require_member
async def upgrade_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    # Edit the existing message instead of sending a new one
    try:
        await q.message.edit_text(UPGRADE_MSG, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=back_to_menu_keyboard())
    except Exception:
        await q.message.reply_text(UPGRADE_MSG, parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=back_to_menu_keyboard())


@require_member
async def dashboard_global_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Main-menu “Dashboard” button — routes to the My Projects list.

    BUG-027 / BUG-028: there is no global dashboard yet, so this button
    intentionally opens the project list (from there the user picks a
    project and lands on its per-project Dashboard).  We delete the
    previous message first (it may be a photo banner) so the new menu
    replaces the welcome card cleanly instead of leaving it stranded
    above the text reply.
    """
    q = update.callback_query
    if q is not None:
        try:
            await q.answer()
        except Exception:
            pass
        try:
            await q.message.delete()
        except Exception:
            pass
    from handlers.my_projects import my_projects_entry
    await my_projects_entry(update, context)
