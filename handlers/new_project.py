"""
/newproject conversation flow — single-message UX.

Fixes:
  - Race condition fixed: tmp_pid now uses UUID instead of user_id
  - asyncio.get_running_loop() instead of deprecated get_event_loop()
  - Duplicate scan code extracted to _run_scan()
  - Per-action cooldown on deploy
  - PAT token cleared from user_data immediately after use
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import uuid

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
from handlers.auth import require_member, require_action_cooldown
from core.file_handler import (
    save_uploaded_file, extract_zip, project_path, clear_project_dir,
)
from core.github_handler import clone_public, clone_private
from core.deployer import finalize_deploy
from core.security import scan_project

log = logging.getLogger(__name__)

# ── Conversation states (named constants — no magic numbers) ─
(
    PROJECT_NAME,
    UPLOAD_TYPE,
    CODE_UPLOAD,
    GITHUB_URL,
    GITHUB_PAT,
    GITHUB_PRIVATE_URL,
    PYTHON_VERSION,
) = range(7)

_SCAN_LABELS = ["File types", "Size check", "Malware scan", "Code safety", "Secrets", "Structure"]


# ── Helper: always edit the "flow message" stored in user_data ──
async def _edit_flow(context: ContextTypes.DEFAULT_TYPE,
                     text: str, reply_markup=None,
                     parse_mode=ParseMode.MARKDOWN) -> None:
    msg = context.user_data.get("flow_msg")
    if msg is None:
        return
    try:
        await msg.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception:
        pass


async def _run_scan(context: ContextTypes.DEFAULT_TYPE, dest: str) -> tuple[bool, list[bool], str]:
    """Run security scan in executor and show progress. Returns (passed, statuses, reason)."""
    await _edit_flow(context,
        "🔍 *Step — Running security scan...*\n\n⬜⬜⬜⬜⬜⬜")

    loop = asyncio.get_running_loop()
    passed, statuses, reason = await loop.run_in_executor(
        None, scan_project, dest,
    )

    scan_lines = "\n".join(
        f"{'✅' if s else '❌'} {label}"
        for s, label in zip(statuses, _SCAN_LABELS)
    )
    await _edit_flow(context, f"🔍 *Scan complete*\n\n{scan_lines}")
    await asyncio.sleep(0.6)
    return passed, statuses, reason


# ────────────────────────────────────────────────────────────
# Entry
# ────────────────────────────────────────────────────────────
@require_member
@require_action_cooldown("deploy")
async def newproject_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    u    = await get_or_create_user(user.id, user.username)
    plan = u.get("plan", "free")
    lim  = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
    cur  = await list_projects(user.id)

    if len(cur) >= lim["projects"]:
        await update.effective_chat.send_message(
            LIMIT_REACHED_MSG.format(used=len(cur), limit=int(lim["projects"]), plan=plan.upper()),
            parse_mode=ParseMode.MARKDOWN,
        )
        return ConversationHandler.END

    context.user_data["new_project"] = {}
    q = getattr(update, "callback_query", None)
    if q:
        await q.answer()
        try:
            await q.message.edit_text(NEW_PROJECT_STEP1, parse_mode=ParseMode.MARKDOWN,
                                      reply_markup=cancel_keyboard())
            context.user_data["flow_msg"] = q.message
        except Exception:
            m = await update.effective_chat.send_message(
                NEW_PROJECT_STEP1, parse_mode=ParseMode.MARKDOWN,
                reply_markup=cancel_keyboard())
            context.user_data["flow_msg"] = m
    else:
        m = await update.effective_chat.send_message(
            NEW_PROJECT_STEP1, parse_mode=ParseMode.MARKDOWN,
            reply_markup=cancel_keyboard())
        context.user_data["flow_msg"] = m
    return PROJECT_NAME


# ────────────────────────────────────────────────────────────
# State 1: Name
# ────────────────────────────────────────────────────────────
async def state_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    try:
        await update.message.delete()
    except Exception:
        pass

    if not valid_project_name(text):
        await _edit_flow(context,
            f"❌ *Invalid name!*\n\n{INVALID_NAME_MSG}",
            reply_markup=cancel_keyboard())
        return PROJECT_NAME

    existing = await get_project_by_name(update.effective_user.id, text)
    if existing is not None:
        await _edit_flow(context,
            NAME_TAKEN_MSG.format(name=text),
            reply_markup=cancel_keyboard())
        return PROJECT_NAME

    context.user_data["new_project"]["name"] = text
    await _edit_flow(context,
        NEW_PROJECT_STEP2.format(name=text),
        reply_markup=upload_type_keyboard())
    return UPLOAD_TYPE


# ────────────────────────────────────────────────────────────
# State 2: Upload type picker
# ────────────────────────────────────────────────────────────
async def state_upload_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q    = update.callback_query
    await q.answer()
    data = q.data
    np   = context.user_data.get("new_project", {})

    mapping = {
        "upload_zip":    ("zip",    UPLOAD_ZIP_PROMPT),
        "upload_py":     ("py",     UPLOAD_PY_PROMPT),
        "upload_pubgh":  ("pubgh",  UPLOAD_PUBGH_PROMPT),
        "upload_privgh": ("privgh", UPLOAD_PRIVGH_PROMPT),
    }
    if data not in mapping:
        return UPLOAD_TYPE

    np["upload_type"] = mapping[data][0]
    await _edit_flow(context, mapping[data][1], reply_markup=cancel_keyboard())
    return CODE_UPLOAD if data in ("upload_zip", "upload_py") else (
        GITHUB_URL if data == "upload_pubgh" else GITHUB_PAT
    )


# ────────────────────────────────────────────────────────────
# State 3A/3D: File upload (ZIP or .py)
# ────────────────────────────────────────────────────────────
async def state_code_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    np          = context.user_data.get("new_project", {})
    upload_type = np.get("upload_type")
    msg         = update.message

    try:
        await msg.delete()
    except Exception:
        pass

    if msg.document is None:
        await _edit_flow(context, "⚠️ Please send a file (📦 ZIP or 🐍 .py).",
                         reply_markup=cancel_keyboard())
        return CODE_UPLOAD

    file_size = msg.document.file_size or 0
    if upload_type == "zip" and file_size > MAX_PROJECT_SIZE_MB * 1024 * 1024:
        await _edit_flow(context, f"❌ ZIP too large (>{MAX_PROJECT_SIZE_MB} MB).",
                         reply_markup=cancel_keyboard())
        return CODE_UPLOAD
    if upload_type == "py" and file_size > MAX_SINGLE_FILE_MB * 1024 * 1024:
        await _edit_flow(context, f"❌ File too large (>{MAX_SINGLE_FILE_MB} MB).",
                         reply_markup=cancel_keyboard())
        return CODE_UPLOAD

    await _edit_flow(context, "📤 *Step 1/4* — Uploading file...")
    tg_file = await msg.document.get_file()
    fname   = msg.document.file_name or ("upload.zip" if upload_type == "zip" else "main.py")
    tmp_dir = tempfile.mkdtemp(prefix="pyhost_up_", dir=TEMP_DIR)
    local   = os.path.join(tmp_dir, fname)
    await tg_file.download_to_drive(custom_path=local)

    # FIXED: Use UUID for tmp_pid — no race condition between users
    tmp_pid = f"pending_{uuid.uuid4().hex[:12]}"
    np["tmp_pid"] = tmp_pid
    clear_project_dir(tmp_pid)
    dest = project_path(tmp_pid)

    await _edit_flow(context, "📦 *Step 2/4* — Extracting files...")
    if upload_type == "zip":
        ok, err = extract_zip(local, dest)
        if not ok:
            await _edit_flow(context, SCAN_FAIL.format(reason=err))
            return ConversationHandler.END
    else:
        os.replace(local, os.path.join(dest, "main.py"))

    passed, statuses, reason = await _run_scan(context, dest)
    if not passed:
        await _edit_flow(context, SCAN_FAIL.format(reason=reason))
        return ConversationHandler.END

    await _edit_flow(context,
        "✅ *Scan passed!*\n\n*Step 4/4* — Select Python version 🐍",
        reply_markup=python_version_keyboard())
    return PYTHON_VERSION


# ────────────────────────────────────────────────────────────
# State 3B: Public GitHub URL
# ────────────────────────────────────────────────────────────
async def state_github_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    url = (update.message.text or "").strip()
    try:
        await update.message.delete()
    except Exception:
        pass

    # FIXED: Use UUID for tmp_pid
    tmp_pid = f"pending_{uuid.uuid4().hex[:12]}"
    context.user_data.get("new_project", {})["tmp_pid"] = tmp_pid

    await _edit_flow(context, "📥 *Step 1/3* — Cloning repository...")
    ok, err = await clone_public(url, tmp_pid)
    if not ok:
        await _edit_flow(context, CLONE_FAIL.format(error=err))
        return ConversationHandler.END

    dest = project_path(tmp_pid)
    passed, statuses, reason = await _run_scan(context, dest)
    if not passed:
        await _edit_flow(context, SCAN_FAIL.format(reason=reason))
        return ConversationHandler.END

    await _edit_flow(context,
        "✅ *Repo cloned & scanned!*\n\nSelect Python version 🐍",
        reply_markup=python_version_keyboard())
    return PYTHON_VERSION


# ────────────────────────────────────────────────────────────
# State 3C: Private GitHub — PAT then URL
# ────────────────────────────────────────────────────────────
async def state_github_pat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    token = (update.message.text or "").strip()
    try:
        await update.message.delete()  # immediately delete the PAT message
    except Exception:
        pass
    # Store token temporarily (will be wiped after clone)
    context.user_data["new_project"]["_pat"] = token
    await _edit_flow(context, PRIVGH_URL_PROMPT,
                     parse_mode=ParseMode.MARKDOWN,
                     reply_markup=cancel_keyboard())
    return GITHUB_PRIVATE_URL


async def state_github_private_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    url = (update.message.text or "").strip()
    try:
        await update.message.delete()
    except Exception:
        pass

    np = context.user_data.get("new_project", {})
    # Pop the PAT immediately — don't leave it in memory
    token = np.pop("_pat", "")

    # FIXED: Use UUID for tmp_pid
    tmp_pid = f"pending_{uuid.uuid4().hex[:12]}"
    np["tmp_pid"] = tmp_pid

    await _edit_flow(context, "📥 *Cloning private repository...*")
    ok, err = await clone_private(url, token, tmp_pid)
    # Wipe token reference explicitly
    token = ""  # noqa: reassignment to local

    if not ok:
        await _edit_flow(context, CLONE_FAIL.format(error=err))
        return ConversationHandler.END

    dest = project_path(tmp_pid)
    passed, statuses, reason = await _run_scan(context, dest)
    if not passed:
        await _edit_flow(context, SCAN_FAIL.format(reason=reason))
        return ConversationHandler.END

    await _edit_flow(context,
        "✅ *Repo cloned & scanned!*\n\nSelect Python version 🐍",
        reply_markup=python_version_keyboard())
    return PYTHON_VERSION


# ────────────────────────────────────────────────────────────
# State 4: Python version → Deploy
# ────────────────────────────────────────────────────────────
async def state_python_version(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q   = update.callback_query
    await q.answer()
    ver = q.data.replace("pyver_", "")
    np  = context.user_data.get("new_project", {})
    name    = np.get("name")
    tmp_pid = np.get("tmp_pid")
    user_id = update.effective_user.id

    steps = [
        "⚙️ *Deploying...* (1/3) Setting up project...",
        "📦 *Deploying...* (2/3) Installing base packages...",
        f"🐍 *Deploying...* (3/3) Starting with Python {ver}...",
    ]
    for step in steps:
        await _edit_flow(context, step)
        await asyncio.sleep(0.8)

    project = await finalize_deploy(user_id, name, ver)
    real_pid = project["project_id"]

    # Move pending files → real project dir
    src = project_path(tmp_pid)
    dst = project_path(real_pid)
    if os.path.isdir(src):
        for entry in os.listdir(src):
            os.replace(os.path.join(src, entry), os.path.join(dst, entry))
        try:
            os.rmdir(src)
        except Exception:
            pass

    context.user_data.pop("new_project", None)

    await _edit_flow(context,
        DEPLOY_DONE.format(name=name, python_version=ver,
                           created_at=fmt_time(project["created_at"])),
        reply_markup=None)
    await asyncio.sleep(0.5)
    await _edit_flow(context,
        PROJECT_PANEL_MSG.format(
            name=name, status_emoji="🔴", status="Stopped",
            python_version=ver, ram_mb="—",
            ram_limit=int(PLAN_LIMITS["free"]["ram_mb"]),
            cpu_pct="—", cpu_limit=int(PLAN_LIMITS["free"]["cpu"] * 100),
            uptime="—", restarts_today=0,
            created_at=fmt_time(project["created_at"]),
        ),
        reply_markup=project_panel_keyboard(real_pid, is_running=False))
    return ConversationHandler.END


# ────────────────────────────────────────────────────────────
# Cancel
# ────────────────────────────────────────────────────────────
async def cancel_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Clean up any pending tmp dir
    np = context.user_data.pop("new_project", None)
    if np and np.get("tmp_pid"):
        try:
            clear_project_dir(np["tmp_pid"])
        except Exception:
            pass

    q = update.callback_query
    if q is not None:
        await q.answer()
        await _edit_flow(context, CANCELLED_MSG)
    elif update.message is not None:
        try:
            await update.message.delete()
        except Exception:
            pass
        await _edit_flow(context, CANCELLED_MSG)
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
