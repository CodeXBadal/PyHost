"""ENV var setup — list, add (manual or .env file), edit, delete."""
from __future__ import annotations

import os
import tempfile
import re

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes, ConversationHandler,
    CallbackQueryHandler, MessageHandler, CommandHandler, filters,
)

from database.models import get_project, list_envs, upsert_env, delete_env
from utils.keyboards import env_menu_keyboard, env_keys_keyboard, back_to_panel_keyboard, cancel_keyboard
from utils.messages import (
    ENV_MENU, ENV_ADD_PROMPT, ENV_UPLOAD_PROMPT, ENV_ADDED, ENV_DELETED, NOT_FOUND,
)
from core.crypto import encrypt
from handlers.auth import require_member

ENV_ADD_INPUT, ENV_UPLOAD_FILE, ENV_EDIT_VALUE = range(200, 203)


def _mask(value: str) -> str:
    if not value:
        return "(empty)"
    if len(value) <= 4:
        return "•" * len(value)
    return value[:2] + "•" * (len(value) - 4) + value[-2:]


async def _render_menu(update: Update, project_id: str, edit: bool = True) -> None:
    proj = await get_project(project_id)
    if proj is None:
        await update.effective_chat.send_message(NOT_FOUND); return
    envs = await list_envs(project_id)
    from core.crypto import decrypt
    if envs:
        var_lines = "\n".join(f"`{e['key']}` = `{_mask(decrypt(e['value']))}`" for e in envs)
    else:
        var_lines = "_(none)_"
    text = ENV_MENU.format(name=proj["name"], vars=var_lines, count=len(envs))
    kb = env_menu_keyboard(project_id, has_vars=bool(envs))
    target = update.callback_query.message if update.callback_query else None
    if target and edit:
        try:
            await target.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb); return
        except Exception:
            pass
    await update.effective_chat.send_message(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


@require_member
async def env_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("env_", "", 1)
    await _render_menu(update, pid)


@require_member
async def env_add_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("envadd_", "", 1)
    context.user_data["env_pid"] = pid
    await q.message.edit_text(ENV_ADD_PROMPT, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=cancel_keyboard())
    return ENV_ADD_INPUT


async def env_add_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pid = context.user_data.pop("env_pid", None)
    if not pid:
        return ConversationHandler.END
    text = (update.message.text or "").strip()
    if "=" not in text:
        await update.message.reply_text("❌ Bad format. Use `KEY=VALUE`.",
                                        parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END
    k, v = text.split("=", 1)
    k, v = k.strip(), v.strip()
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", k):
        await update.message.reply_text("❌ Invalid key. Use letters/digits/underscores.")
        return ConversationHandler.END
    await upsert_env(pid, k, encrypt(v))
    await update.message.reply_text(ENV_ADDED.format(key=k),
                                    parse_mode=ParseMode.MARKDOWN,
                                    reply_markup=back_to_panel_keyboard(pid))
    return ConversationHandler.END


@require_member
async def env_upload_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("envup_", "", 1)
    context.user_data["env_pid"] = pid
    await q.message.edit_text(ENV_UPLOAD_PROMPT, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=cancel_keyboard())
    return ENV_UPLOAD_FILE


async def env_upload_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pid = context.user_data.pop("env_pid", None)
    if not pid or update.message.document is None:
        return ConversationHandler.END
    if (update.message.document.file_size or 0) > 64 * 1024:
        await update.message.reply_text("❌ .env file too large (>64 KB).")
        return ConversationHandler.END
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".env")
    tmp.close()
    tg = await update.message.document.get_file()
    await tg.download_to_drive(custom_path=tmp.name)

    n = 0
    with open(tmp.name, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip(); v = v.strip().strip("'\"")
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", k):
                await upsert_env(pid, k, encrypt(v)); n += 1
    try:
        os.remove(tmp.name)
    except Exception:
        pass
    await update.message.reply_text(f"✅ Imported {n} variables.",
                                    reply_markup=back_to_panel_keyboard(pid))
    return ConversationHandler.END


@require_member
async def env_delete_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("envdel_", "", 1)
    envs = await list_envs(pid)
    keys = [e["key"] for e in envs]
    await q.message.edit_text(
        "🗑️ Pick a variable to delete:",
        reply_markup=env_keys_keyboard(pid, keys, action="del"),
    )


@require_member
async def env_edit_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    pid = q.data.replace("envedit_", "", 1)
    envs = await list_envs(pid)
    keys = [e["key"] for e in envs]
    await q.message.edit_text(
        "✏️ Pick a variable to edit:",
        reply_markup=env_keys_keyboard(pid, keys, action="edit"),
    )
    return ConversationHandler.END   # actual edit value via callback `envk_edit_...`


@require_member
async def env_key_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    m = re.match(r"^envk_(edit|del)_([0-9a-f]{12})_(.+)$", q.data)
    if not m:
        return ConversationHandler.END
    action, pid, key = m.group(1), m.group(2), m.group(3)
    if action == "del":
        await delete_env(pid, key)
        await q.message.edit_text(ENV_DELETED.format(key=key),
                                  parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=back_to_panel_keyboard(pid))
        return ConversationHandler.END
    # edit → ask new value
    context.user_data["env_pid"]  = pid
    context.user_data["env_key"]  = key
    await q.message.edit_text(f"Send the *new value* for `{key}`:",
                              parse_mode=ParseMode.MARKDOWN,
                              reply_markup=cancel_keyboard())
    return ENV_EDIT_VALUE


async def env_edit_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pid = context.user_data.pop("env_pid", None)
    key = context.user_data.pop("env_key", None)
    if not pid or not key:
        return ConversationHandler.END
    val = (update.message.text or "").strip()
    await upsert_env(pid, key, encrypt(val))
    await update.message.reply_text(f"✅ `{key}` updated.",
                                    parse_mode=ParseMode.MARKDOWN,
                                    reply_markup=back_to_panel_keyboard(pid))
    return ConversationHandler.END


async def env_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("env_pid", None)
    context.user_data.pop("env_key", None)
    q = update.callback_query
    if q:
        await q.answer()
        try: await q.message.edit_text("❌ Cancelled.")
        except Exception: pass
    return ConversationHandler.END


def build_env_handlers() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(env_add_entry,    pattern=r"^envadd_[0-9a-f]{12}$"),
            CallbackQueryHandler(env_upload_entry, pattern=r"^envup_[0-9a-f]{12}$"),
            CallbackQueryHandler(env_key_action,   pattern=r"^envk_(edit)_[0-9a-f]{12}_.+$"),
        ],
        states={
            ENV_ADD_INPUT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, env_add_save)],
            ENV_UPLOAD_FILE:  [MessageHandler(filters.Document.ALL, env_upload_save)],
            ENV_EDIT_VALUE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, env_edit_save)],
        },
        fallbacks=[
            CommandHandler("cancel", env_cancel),
            CallbackQueryHandler(env_cancel, pattern=r"^cancel_flow$"),
        ],
        per_chat=True, allow_reentry=True, name="env_setup",
    )
