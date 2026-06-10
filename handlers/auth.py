"""
Force-channel-join middleware + rate-limit gate.

`require_member()` is a decorator used by every command/callback entry
point. It also performs the global Redis-based rate limit.
"""
from __future__ import annotations

import functools
import logging
from typing import Callable

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import FORCE_JOIN_CHANNEL
from database.models import get_or_create_user
from database.redis_client import redis_client
from utils.keyboards import force_join_keyboard
from utils.messages import FORCE_JOIN_MSG, RATE_LIMITED_MSG

log = logging.getLogger(__name__)


async def _is_channel_member(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    if not FORCE_JOIN_CHANNEL:
        return True
    try:
        m = await context.bot.get_chat_member(FORCE_JOIN_CHANNEL, user_id)
        return m.status in ("member", "administrator", "creator")
    except Exception as exc:
        log.debug("get_chat_member failed for %s: %s", user_id, exc)
        # If the bot isn't admin of the channel we can't verify → allow
        return True


async def _send_join_prompt(update: Update) -> None:
    target = update.effective_chat
    if target is None:
        return
    await target.send_message(
        FORCE_JOIN_MSG,
        reply_markup=force_join_keyboard(FORCE_JOIN_CHANNEL),
        parse_mode=ParseMode.MARKDOWN,
    )


def require_member(func: Callable):
    """Decorator: enforce channel-join + rate limit + ban-check before handler."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kw):
        user = update.effective_user
        if user is None:
            return await func(update, context, *args, **kw)

        # ensure user row exists
        u = await get_or_create_user(user.id, user.username)
        if u.get("is_banned"):
            try:
                await update.effective_chat.send_message("🚫 You are banned from using this bot.")
            except Exception:
                pass
            return

        # rate limit
        try:
            if await redis_client.is_rate_limited(user.id):
                ttl = await redis_client.rate_limit_ttl(user.id)
                await update.effective_chat.send_message(
                    RATE_LIMITED_MSG.format(seconds=ttl),
                    parse_mode=ParseMode.MARKDOWN,
                )
                return
        except Exception as exc:
            log.debug("Redis rate-limit check skipped: %s", exc)

        # force join
        if FORCE_JOIN_CHANNEL and not await _is_channel_member(context, user.id):
            await _send_join_prompt(update)
            return

        return await func(update, context, *args, **kw)
    return wrapper


async def auth_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the ✅ I Joined button."""
    q = update.callback_query
    if q is None:
        return
    await q.answer()
    user = update.effective_user
    if await _is_channel_member(context, user.id):
        from handlers.start import _send_start_card
        await q.message.delete()
        await _send_start_card(update, context)
    else:
        await q.answer("You still aren't a member — please join first.", show_alert=True)
