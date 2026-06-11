"""
/newproject conversation flow.

States (see STATES dict): name → upload type → source → python version → deploy.
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes, ConversationHandler,
    CommandHandler, CallbackQueryHandler, MessageHandler, filters,
)

from config import PLAN_LIMITS, TEMP_DIR, MAX_PROJECT_SIZE_MB, MAX_SINGLE_FILE_MB
from database.models import (
    get_or_create_user, get_project_by_name, list_projects,
)
from utils.animations import upload_progress, scan_animation, deploy_animation
from utils.helpers import valid_project_name, fmt_time
from utils.keyboards import (
    upload_type_keyboard, python_version_keyboard, cancel_keyboard,
    project_panel_keyboard,
)
from utils.messages import (
    NEW_PROJECT_STEP1, NEW_PROJECT_STEP2, INVALID_NAME_MSG, NAME_TAKEN_MSG,
    LIMIT_REACHED_MSG, UPLOAD_ZIP_PROMPT, UPLOAD_PY_PROMPT,
    UPLOAD_PUBGH_PROMPT, UPLOAD_PRIVGH_PROMPT, PRIVGH_URL_PROMPT,
    CLONE_SUCCESS, CLONE_FAIL, SCAN_FAIL, DEPLOY_DONE, CANCELLED_MSG,
    PROJECT_PANEL_MSG,
)
from handlers.auth import require_member
from core.file_handler import (
    save_uploaded_file, extract_zip, project_path, clear_project_dir,
)
from core.github_handler import clone_public, clone_private
from core.deployer import run_security_scan, finalize_deploy

log = logging.getLogger(__name__)

# ConversationHandler states
PROJECT_NAME, UPLOAD_TYPE, CODE_UPLOAD, GITHUB_URL, GITHUB_PAT, \
    GITHUB_PRIVATE_URL, PYTHON_VERSION = range(7)


# ────────────────────────────────────────────────────────────
# entry
# ────────────────────────────────────────────────────────────
@require_member
async def newproject_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    u = await get_or_create_user(user.id, user.username)
    plan = u.get("plan", "free")
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
    cur = await list_projects(user.id)
    if len(cur) >= limits["projects"]:
        await update.effective_chat.send_message(
            LIMIT_REACHED_MSG.format(used=len(cur), limit=int(limits["projects"]), plan=plan.upper()),
            parse_mode=ParseMode.MARKDOWN,
        )
        return ConversationHandler.END

    context.user_data["new_project"] = {}
    await update.effective_chat.send_message(
        NEW_PROJECT_STEP1, parse_mode=ParseMode.MARKDOWN,
        reply_markup=cancel_keyboard(),
    )
    return PROJECT_NAME


# ────────────────────────────────────────────────────────────
# state 1: name
# ────────────────────────────────────────────────────────────
async def state_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if not valid_project_name(text):
        await update.message.reply_text(INVALID_NAME_MSG)
        return PROJECT_NAME

    existing = await get_project_by_name(update.effective_user.id, text)
    if existing is not None:
        await update.message.reply_text(NAME_TAKEN_MSG.format(name=text))
        return PROJECT_NAME

    context.user_data["new_project"]["name"] = text
    await update.message.reply_text(
        NEW_PROJECT_STEP2.format(name=text),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=upload_type_keyboard(),
    )
    return UPLOAD_TYPE


# ────────────────────────────────────────────────────────────
# state 2: upload type pick
# ────────────────────────────────────────────────────────────
async def state_upload_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    data = q.data

    np = context.user_data.get("new_project", {})
    if data == "upload_zip":
        np["upload_type"] = "zip"
        await q.message.edit_text(UPLOAD_ZIP_PROMPT, reply_markup=cancel_keyboard())
        return CODE_UPLOAD
    if data == "upload_py":
        np["upload_type"] = "py"
        await q.message.edit_text(UPLOAD_PY_PROMPT, reply_markup=cancel_keyboard())
        return CODE_UPLOAD
    if data == "upload_pubgh":
        np["upload_type"] = "pubgh"
        await q.message.edit_text(UPLOAD_PUBGH_PROMPT, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=cancel_keyboard())
        return GITHUB_URL
    if data == "upload_privgh":
        np["upload_type"] = "privgh"
        await q.message.edit_text(UPLOAD_PRIVGH_PROMPT, parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=cancel_keyboard())
        return GITHUB_PAT
    return UPLOAD_TYPE


# ────────────────────────────────────────────────────────────
# state 3A/3D: file upload (zip or .py)
# FIX: scan runs in executor (non-blocking), animation and next step
#      are sent as a NEW message (not reply to status_msg) to avoid
#      edit-chain failures that caused the flow to stall at step 7.
# ────────────────────────────────────────────────────────────
async def state_code_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    np = context.user_data.get("new_project", {})
    upload_type = np.get("upload_type")
    msg = update.message

    if msg.document is None:
        await msg.reply_text("Please send a file (📦 ZIP or 🐍 .py).")
        return CODE_UPLOAD

    file_size = msg.document.file_size or 0
    if upload_type == "zip" and file_size > MAX_PROJECT_SIZE_MB * 1024 * 1024:
        await msg.reply_text(f"❌ ZIP too large (>{MAX_PROJECT_SIZE_MB} MB).")
        return CODE_UPLOAD
    if upload_type == "py" and file_size > MAX_SINGLE_FILE_MB * 1024 * 1024:
        await msg.reply_text(f"❌ File too large (>{MAX_SINGLE_FILE_MB} MB).")
        return CODE_UPLOAD

    # ── Step 1: Upload ──────────────────────────────────────
    status_msg = await msg.reply_text("📤 *Uploading your file...*", parse_mode=ParseMode.MARKDOWN)
    await upload_progress(status_msg)

    # download
    tg_file = await msg.document.get_file()
    fname = msg.document.file_name or ("upload.zip" if upload_type == "zip" else "main.py")
    tmp_dir = tempfile.mkdtemp(prefix="pyhost_up_", dir=TEMP_DIR)
    local = os.path.join(tmp_dir, fname)
    await tg_file.download_to_drive(custom_path=local)

    # prepare project dir
    user_id = update.effective_user.id
    tmp_pid = f"pending_{user_id}"          # temp slug; replaced with real id after create
    clear_project_dir(tmp_pid)
    dest = project_path(tmp_pid)

    # ── Step 2: Extract ─────────────────────────────────────
    if upload_type == "zip":
        ok, err = extract_zip(local, dest)
        if not ok:
            await status_msg.edit_text(SCAN_FAIL.format(reason=err), parse_mode=ParseMode.MARKDOWN)
            return ConversationHandler.END
    else:
        # single .py — drop into project root as main.py
        os.replace(local, os.path.join(dest, "main.py"))

    # ── Step 3: Security scan ───────────────────────────────
    # FIX: run_security_scan wraps a synchronous function — run it in
    # the default executor so it doesn't block the event loop.
    # This prevents the bot from appearing "frozen" during large ZIPs.
    loop = asyncio.get_event_loop()
    passed, statuses, reason = await loop.run_in_executor(
        None, __import__("core.security", fromlist=["scan_project"]).scan_project, dest
    )

    # Send scan animation as a FRESH message (not edit of status_msg).
    # This avoids "message not modified" / edit-chain failures that stalled the flow.
    scan_msg = await msg.reply_text("🔍 *Scanning files...*", parse_mode=ParseMode.MARKDOWN)
    await scan_animation(scan_msg, statuses)

    if not passed:
        await msg.reply_text(SCAN_FAIL.format(reason=reason), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    # ── Step 4: Python version select ──────────────────────
    context.user_data["new_project"]["tmp_pid"] = tmp_pid
    # FIX: send Python version prompt as a brand-new message so it always
    # arrives even if scan_msg edit had any issue.
    await msg.reply_text(
        "*Step 3/4* — Select Python version 🐍",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=python_version_keyboard(),
    )
    return PYTHON_VERSION


# ────────────────────────────────────────────────────────────
# state 3B: public github url
# ────────────────────────────────────────────────────────────
async def state_github_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    url = (update.message.text or "").strip()
    user_id = update.effective_user.id
    tmp_pid = f"pending_{user_id}"
    status_msg = await update.message.reply_text("🔍 *Validating GitHub repository...*",
                                                 parse_mode=ParseMode.MARKDOWN)
    await asyncio.sleep(0.4)
    await status_msg.edit_text("📥 *Cloning repository...*", parse_mode=ParseMode.MARKDOWN)
    ok, err = await clone_public(url, tmp_pid)
    if not ok:
        await status_msg.edit_text(CLONE_FAIL.format(error=err))
        return ConversationHandler.END
    await status_msg.edit_text(CLONE_SUCCESS)
    await asyncio.sleep(0.3)

    dest = project_path(tmp_pid)
    loop = asyncio.get_event_loop()
    passed, statuses, reason = await loop.run_in_executor(
        None, __import__("core.security", fromlist=["scan_project"]).scan_project, dest
    )
    scan_msg = await update.message.reply_text("🔍 *Scanning files...*",
                                               parse_mode=ParseMode.MARKDOWN)
    await scan_animation(scan_msg, statuses)
    if not passed:
        await update.message.reply_text(SCAN_FAIL.format(reason=reason), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    context.user_data["new_project"]["tmp_pid"] = tmp_pid
    await update.message.reply_text(
        "*Step 3/4* — Select Python version 🐍",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=python_version_keyboard(),
    )
    return PYTHON_VERSION


# ────────────────────────────────────────────────────────────
# state 3C: private github (PAT first, then URL)
# ────────────────────────────────────────────────────────────
async def state_github_pat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    token = (update.message.text or "").strip()
    context.user_data["new_project"]["_pat"] = token
    # delete the message containing the PAT for safety
    try:
        await update.message.delete()
    except Exception:
        pass
    await update.effective_chat.send_message(PRIVGH_URL_PROMPT,
                                             parse_mode=ParseMode.MARKDOWN,
                                             reply_markup=cancel_keyboard())
    return GITHUB_PRIVATE_URL


async def state_github_private_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    url = (update.message.text or "").strip()
    np = context.user_data.get("new_project", {})
    token = np.pop("_pat", "")
    user_id = update.effective_user.id
    tmp_pid = f"pending_{user_id}"
    status_msg = await update.message.reply_text("📥 *Cloning private repository...*",
                                                 parse_mode=ParseMode.MARKDOWN)
    ok, err = await clone_private(url, token, tmp_pid)
    token = ""  # wipe local
    if not ok:
        await status_msg.edit_text(CLONE_FAIL.format(error=err))
        return ConversationHandler.END
    await status_msg.edit_text(CLONE_SUCCESS + "\n(Token wiped from memory ✅)",
                               parse_mode=ParseMode.MARKDOWN)

    dest = project_path(tmp_pid)
    loop = asyncio.get_event_loop()
    passed, statuses, reason = await loop.run_in_executor(
        None, __import__("core.security", fromlist=["scan_project"]).scan_project, dest
    )
    scan_msg = await update.message.reply_text("🔍 *Scanning files...*",
                                               parse_mode=ParseMode.MARKDOWN)
    await scan_animation(scan_msg, statuses)
    if not passed:
        await update.message.reply_text(SCAN_FAIL.format(reason=reason), parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    np["tmp_pid"] = tmp_pid
    await update.message.reply_text(
        "*Step 3/4* — Select Python version 🐍",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=python_version_keyboard(),
    )
    return PYTHON_VERSION


# ────────────────────────────────────────────────────────────
# state 4: python version → deploy
# ────────────────────────────────────────────────────────────
async def state_python_version(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    ver = q.data.replace("pyver_", "")
    np  = context.user_data.get("new_project", {})
    name = np.get("name")
    tmp_pid = np.get("tmp_pid")
    user_id = update.effective_user.id

    deploy_msg = await q.message.edit_text("🐳 *Creating Docker container...*",
                                           parse_mode=ParseMode.MARKDOWN)
    await deploy_animation(deploy_msg, ver)

    # finalize: create project row + container + move pending files to real project dir
    project = await finalize_deploy(user_id, name, ver)
    real_pid = project["project_id"]

    # move files from pending_<uid> to <real_pid>
    src = project_path(tmp_pid)
    dst = project_path(real_pid)
    if os.path.isdir(src):
        # dst already created by finalize_deploy via create_container; merge files in
        for entry in os.listdir(src):
            os.replace(os.path.join(src, entry), os.path.join(dst, entry))
        try:
            os.rmdir(src)
        except Exception:
            pass

    context.user_data.pop("new_project", None)

    await deploy_msg.reply_text(
        DEPLOY_DONE.format(
            name=name,
            python_version=ver,
            created_at=fmt_time(project["created_at"]),
        ),
        parse_mode=ParseMode.MARKDOWN,
    )
    # open the project panel
    await deploy_msg.reply_text(
        PROJECT_PANEL_MSG.format(
            name=name,
            status_emoji="🔴",
            status="Stopped",
            python_version=ver,
            ram_mb="—",
            ram_limit=PLAN_LIMITS["free"]["ram_mb"],
            cpu_pct="—",
            cpu_limit=int(PLAN_LIMITS["free"]["cpu"] * 100),
            uptime="—",
            restarts_today=0,
            created_at=fmt_time(project["created_at"]),
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=project_panel_keyboard(real_pid, is_running=False),
    )
    return ConversationHandler.END


# ────────────────────────────────────────────────────────────
# cancel
# ────────────────────────────────────────────────────────────
async def cancel_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("new_project", None)
    q = update.callback_query
    if q is not None:
        await q.answer()
        try:
            await q.message.edit_text(CANCELLED_MSG)
        except Exception:
            await q.message.reply_text(CANCELLED_MSG)
    elif update.message is not None:
        await update.message.reply_text(CANCELLED_MSG)
    return ConversationHandler.END


# ────────────────────────────────────────────────────────────
# ConversationHandler wiring
# ────────────────────────────────────────────────────────────
def build_new_project_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("newproject", newproject_entry),
            CallbackQueryHandler(newproject_entry, pattern=r"^new_project$"),
        ],
        states={
            PROJECT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, state_name),
            ],
            UPLOAD_TYPE: [
                CallbackQueryHandler(state_upload_type,
                                     pattern=r"^upload_(zip|py|pubgh|privgh)$"),
            ],
            CODE_UPLOAD: [
                MessageHandler(filters.Document.ALL, state_code_upload),
            ],
            GITHUB_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, state_github_url),
            ],
            GITHUB_PAT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, state_github_pat),
            ],
            GITHUB_PRIVATE_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, state_github_private_url),
            ],
            PYTHON_VERSION: [
                CallbackQueryHandler(state_python_version, pattern=r"^pyver_"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_flow),
            CallbackQueryHandler(cancel_flow, pattern=r"^cancel_flow$"),
        ],
        per_chat=True,
        allow_reentry=True,
        name="new_project",
    )
