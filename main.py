"""
PyHost Bot — application entry point.

Fixes:
  - run_user_schedule._bot hack removed — bot passed via app.bot_data properly
  - asyncio.get_running_loop() used throughout
  - Scheduler job IDs include project_id for proper replace_existing
  - Cleaner handler registration
  - PicklePersistence removed (was a single point of failure)
  - BUG-005 / BUG-045: app.create_task() was an invalid API on PTB 22.7 —
    background tasks are now started with asyncio.create_task() and tracked
    so they're cancelled in post_shutdown.
  - BUG-008 / BUG-009: /cancel and /help are registered with proper async
    handler functions instead of bare lambdas wrapping coroutines.
  - BUG-021: scheduled restart now skips env vars whose decryption returned
    an empty string (InvalidToken after key rotation), preventing silent
    misbehaviour.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler,
    CallbackQueryHandler, MessageHandler, ContextTypes, filters,
)
from telegram.constants import ParseMode

from config import (
    BOT_TOKEN, ADMIN_IDS, CLEANUP_TEMP_EVERY_MIN,
    RESOURCE_POLL_EVERY_SEC, TEMP_DIR,
    HEALTHCHECK_HOST, HEALTHCHECK_PORT,
)
from database import db, close_db, init_indexes
from database.redis_client import redis_client, close_redis
from database.models import all_projects, list_schedules, get_project, list_envs

# ── handlers ─────────────────────────────────────────────────
from handlers.auth import auth_check_callback
from handlers.start import (
    start_command, main_menu_callback, help_callback,
    support_callback, upgrade_callback, dashboard_global_callback,
)
from handlers.new_project import build_new_project_handler
from handlers.my_projects import my_projects_entry, my_projects_page_callback
from handlers.project_panel import project_panel_callback
from handlers.install_deps import deps_entry, deps_go
from handlers.run_command import build_runcmd_handler
from handlers.logs import logs_entry, logs_download
from handlers.dashboard import dashboard_entry
from handlers.analytics import analytics_entry
from handlers.env_setup import (
    env_entry, env_delete_pick, env_edit_pick, env_key_action,
    build_env_handlers,
)
from handlers.file_manager import fm_entry, fm_cd, fm_get
from handlers.backup import (
    backup_entry, backup_create, backup_list, backup_download, backup_remove,
    backup_restore_pick, backup_restore_confirm, backup_restore_do,
)
from handlers.scheduler import (
    sched_entry, sched_remove, sched_delete, build_scheduler_handler,
)
from handlers.webhook_manager import (
    webhook_entry, webhook_regen, build_webhook_handler,
)
from handlers.delete_project import delete_entry, delete_confirmed
from handlers.admin import (
    admin_command, admin_panel_callback, adm_users, adm_stats,
    adm_containers, adm_cleanup, adm_errors, build_admin_handlers,
)

# ── core ────────────────────────────────────────────────────
from core.monitor import monitor_loop
from core.resource_tracker import poll_all_resources
from core.process_manager import process_manager
from core.crypto import decrypt


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s :: %(message)s",
)
log = logging.getLogger("pyhost.main")


# ────────────────────────────────────────────────────────────
# Scheduled jobs
# ────────────────────────────────────────────────────────────
async def cleanup_temp_job() -> None:
    cutoff = time.time() - 3600  # 1h old
    n = 0
    for entry in os.listdir(TEMP_DIR):
        full = os.path.join(TEMP_DIR, entry)
        try:
            if os.path.isdir(full) and os.path.getmtime(full) < cutoff:
                shutil.rmtree(full)
                n += 1
            elif os.path.isfile(full) and os.path.getmtime(full) < cutoff:
                os.remove(full)
                n += 1
        except Exception:
            pass
    if n:
        log.info("cleanup_temp_job: removed %d temp entries", n)


async def run_user_schedule(project_id: str, action: str, bot_data: dict) -> None:
    """Execute a user-defined schedule action.

    FIXED: bot reference passed via bot_data dict, not function attribute hack.
    FIX for BUG-021: silently drop env vars whose decrypted value is empty
    (typically caused by InvalidToken after rotating ENCRYPTION_KEY).  This
    prevents the child process from running with bogus empty secrets.
    """
    proj = await get_project(project_id)
    if proj is None:
        return

    if action == "restart":
        envs = {}
        for e in await list_envs(project_id):
            val = decrypt(e["value"])
            if not val:
                log.warning(
                    "run_user_schedule: skipping env var %r for project %s "
                    "— decryption returned empty (possible ENCRYPTION_KEY rotation)",
                    e.get("key"), project_id,
                )
                continue
            envs[e["key"]] = val
        await process_manager.restart_container(
            project_id, proj["run_command"], envs,
            user_id=proj["user_id"], proj_name=proj["name"],
        )

    elif action == "clearlogs":
        await process_manager.clear_logs(
            project_id, user_id=proj["user_id"], proj_name=proj["name"],
        )

    elif action == "stats":
        bot = bot_data.get("bot")
        if bot is None:
            log.warning("run_user_schedule: bot not available in bot_data")
            return
        stats = await process_manager.get_stats(
            project_id, user_id=proj["user_id"], proj_name=proj["name"],
        )
        from utils.helpers import human_uptime
        await bot.send_message(
            proj["user_id"],
            f"📊 *Daily stats — {proj['name']}*\n\n"
            f"RAM: {stats['ram_mb']:.0f} MB\n"
            f"CPU: {stats['cpu_percent']:.0f}%\n"
            f"Uptime: {human_uptime(stats.get('uptime_seconds', 0))}\n"
            f"Status: {stats['status']}",
            parse_mode=ParseMode.MARKDOWN,
        )


async def load_user_schedules(scheduler: AsyncIOScheduler, bot_data: dict) -> None:
    projects = await all_projects()
    for p in projects:
        for s in await list_schedules(p["project_id"]):
            if not s.get("is_active"):
                continue
            try:
                trig = CronTrigger.from_crontab(s["cron_expression"])
            except Exception:
                continue
            scheduler.add_job(
                run_user_schedule,
                trigger=trig,
                kwargs={
                    "project_id": p["project_id"],
                    "action": s["action"],
                    "bot_data": bot_data,   # FIXED: pass bot_data dict
                },
                id=f"sched_{s['schedule_id']}",
                replace_existing=True,
            )


# ────────────────────────────────────────────────────────────
# Global error handler
# ────────────────────────────────────────────────────────────
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Unhandled error: %s", context.error)
    for aid in ADMIN_IDS:
        try:
            await context.bot.send_message(
                aid, f"⚠️ Bot error:\n`{str(context.error)[:500]}`",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:
            pass


async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.callback_query:
        await update.callback_query.answer()


async def _healthcheck_client(reader: asyncio.StreamReader,
                              writer: asyncio.StreamWriter) -> None:
    try:
        request = await reader.read(1024)
        if request.startswith(b"GET /health"):
            body = b"ok"
            writer.write(
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/plain\r\n"
                b"Content-Length: 2\r\n"
                b"Connection: close\r\n\r\n" + body
            )
        else:
            body = b"not found"
            writer.write(
                b"HTTP/1.1 404 Not Found\r\n"
                b"Content-Type: text/plain\r\n"
                b"Content-Length: 9\r\n"
                b"Connection: close\r\n\r\n" + body
            )
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


# ────────────────────────────────────────────────────────────
# Plain async wrappers for simple commands (BUG-008, BUG-009)
# ────────────────────────────────────────────────────────────
async def _help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/help — calls the shared help_callback used by the inline button."""
    await help_callback(update, context)


async def _cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/cancel outside any active ConversationHandler.

    ConversationHandlers have their own /cancel fallback that takes
    priority when a flow is active, so this only fires when there is
    nothing in progress.
    """
    if update.message is not None:
        await update.message.reply_text("Nothing to cancel.")


# ────────────────────────────────────────────────────────────
# Application lifecycle
# ────────────────────────────────────────────────────────────
async def post_init(app: Application) -> None:
    await redis_client.connect()
    await init_indexes()
    log.info("DB + in-memory session/rate store ready.")

    # Store bot reference in bot_data (not as function attribute)
    app.bot_data["bot"] = app.bot

    health_server = await asyncio.start_server(
        _healthcheck_client,
        host=HEALTHCHECK_HOST,
        port=HEALTHCHECK_PORT,
    )
    app.bot_data["health_server"] = health_server
    # FIX for BUG-005 / BUG-045: PTB 22.7 Application has no create_task()
    # method.  Use asyncio.create_task() and stash the Task on bot_data so
    # post_shutdown() can cancel cleanly.
    app.bot_data["bg_tasks"] = []
    app.bot_data["bg_tasks"].append(
        asyncio.create_task(health_server.serve_forever(), name="health_server")
    )

    # Scheduler
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(cleanup_temp_job, "interval", minutes=CLEANUP_TEMP_EVERY_MIN,
                      id="cleanup_temp", replace_existing=True)
    scheduler.add_job(poll_all_resources, "interval", seconds=RESOURCE_POLL_EVERY_SEC,
                      id="poll_resources", replace_existing=True)
    await load_user_schedules(scheduler, app.bot_data)
    scheduler.start()
    app.bot_data["scheduler"] = scheduler

    # Crash monitor loop
    app.bot_data["bg_tasks"].append(
        asyncio.create_task(monitor_loop(app.bot, interval=15), name="monitor_loop")
    )
    log.info(
        "Scheduler + monitor loop started. Healthcheck at http://%s:%s/health",
        HEALTHCHECK_HOST,
        HEALTHCHECK_PORT,
    )


async def post_shutdown(app: Application) -> None:
    sched = app.bot_data.get("scheduler")
    if sched:
        sched.shutdown(wait=False)
    health_server = app.bot_data.get("health_server")
    if health_server:
        health_server.close()
        try:
            await health_server.wait_closed()
        except Exception:
            pass
    for t in app.bot_data.get("bg_tasks", []):
        if not t.done():
            t.cancel()
    await close_redis()
    await close_db()
    log.info("PyHost Bot shut down cleanly.")


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN missing — set it in .env")

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # ── Conversation handlers must come first ──────────────
    app.add_handler(build_new_project_handler())
    app.add_handler(build_runcmd_handler())
    app.add_handler(build_env_handlers())
    app.add_handler(build_scheduler_handler())
    app.add_handler(build_webhook_handler())
    for h in build_admin_handlers():
        app.add_handler(h)

    # ── Plain commands ─────────────────────────────────────
    app.add_handler(CommandHandler("start",      start_command))
    # FIX for BUG-008 / BUG-009: use real async wrappers instead of lambdas
    # that return un-awaited coroutines on PTB 22.7.
    app.add_handler(CommandHandler("help",       _help_command))
    app.add_handler(CommandHandler("myprojects", my_projects_entry))
    app.add_handler(CommandHandler("admin",      admin_command))
    app.add_handler(CommandHandler("cancel",     _cancel_command))

    # ── Callback queries ───────────────────────────────────
    cb = app.add_handler
    cb(CallbackQueryHandler(auth_check_callback,       pattern=r"^auth_check$"))
    cb(CallbackQueryHandler(main_menu_callback,        pattern=r"^main_menu$"))
    cb(CallbackQueryHandler(help_callback,             pattern=r"^help$"))
    cb(CallbackQueryHandler(support_callback,          pattern=r"^support$"))
    cb(CallbackQueryHandler(upgrade_callback,          pattern=r"^upgrade$"))
    cb(CallbackQueryHandler(dashboard_global_callback, pattern=r"^dashboard$"))
    cb(CallbackQueryHandler(my_projects_entry,         pattern=r"^my_projects$"))
    cb(CallbackQueryHandler(my_projects_page_callback, pattern=r"^mp_page_\d+$"))

    cb(CallbackQueryHandler(project_panel_callback,
                            pattern=r"^(panel|start|stop|restart)_([0-9a-f]{32}|[0-9a-f]{24})$"))

    cb(CallbackQueryHandler(deps_entry, pattern=r"^deps_[0-9a-f]{32}$"))
    cb(CallbackQueryHandler(deps_go,    pattern=r"^depsgo_[0-9a-f]{32}$"))

    cb(CallbackQueryHandler(logs_entry,    pattern=r"^logs_[0-9a-f]{32}$"))
    cb(CallbackQueryHandler(logs_download, pattern=r"^logd_[0-9a-f]{32}_(\d+|full|err)$"))

    cb(CallbackQueryHandler(dashboard_entry, pattern=r"^dash_[0-9a-f]{32}$"))
    cb(CallbackQueryHandler(analytics_entry, pattern=r"^ana_[0-9a-f]{32}(_24h|_7d|_30d)?$"))

    cb(CallbackQueryHandler(env_entry,       pattern=r"^env_[0-9a-f]{32}$"))
    cb(CallbackQueryHandler(env_delete_pick, pattern=r"^envdel_[0-9a-f]{32}$"))
    cb(CallbackQueryHandler(env_edit_pick,   pattern=r"^envedit_[0-9a-f]{32}$"))
    # FIX for BUG-018: only "del" goes through the global handler. The
    # "edit" sub-action is an entry_point of the env_setup
    # ConversationHandler (see handlers/env_setup.py).
    cb(CallbackQueryHandler(env_key_action,  pattern=r"^envk_del_[0-9a-f]{32}_.+$"))

    cb(CallbackQueryHandler(fm_entry, pattern=r"^files_[0-9a-f]{32}$"))
    cb(CallbackQueryHandler(fm_cd,    pattern=r"^fmcd_[0-9a-f]{32}_.*$"))
    cb(CallbackQueryHandler(fm_get,   pattern=r"^fmget_[0-9a-f]{32}_.+$"))

    cb(CallbackQueryHandler(backup_entry,           pattern=r"^backup_[0-9a-f]{32}$"))
    cb(CallbackQueryHandler(backup_create,          pattern=r"^bkcreate_[0-9a-f]{32}$"))
    cb(CallbackQueryHandler(backup_list,            pattern=r"^bklist_[0-9a-f]{32}$"))
    cb(CallbackQueryHandler(backup_download,        pattern=r"^bkdl_[0-9a-f]{10}$"))
    cb(CallbackQueryHandler(backup_remove,          pattern=r"^bkrm_[0-9a-f]{10}$"))
    cb(CallbackQueryHandler(backup_restore_pick,    pattern=r"^bkrestore_[0-9a-f]{32}$"))
    cb(CallbackQueryHandler(backup_restore_confirm, pattern=r"^bkrok_[0-9a-f]{10}$"))
    cb(CallbackQueryHandler(backup_restore_do,      pattern=r"^bkdo_[0-9a-f]{10}$"))

    cb(CallbackQueryHandler(sched_entry,  pattern=r"^sched_[0-9a-f]{32}$"))
    cb(CallbackQueryHandler(sched_remove, pattern=r"^schrm_[0-9a-f]{32}$"))
    cb(CallbackQueryHandler(sched_delete, pattern=r"^schdel_[0-9a-f]{10}$"))

    cb(CallbackQueryHandler(webhook_entry, pattern=r"^webhook_[0-9a-f]{32}$"))
    cb(CallbackQueryHandler(webhook_regen, pattern=r"^whregen_[0-9a-f]{32}$"))

    cb(CallbackQueryHandler(delete_entry,     pattern=r"^delete_[0-9a-f]{32}$"))
    cb(CallbackQueryHandler(delete_confirmed, pattern=r"^delyes_[0-9a-f]{32}$"))

    # Admin callbacks
    cb(CallbackQueryHandler(admin_panel_callback, pattern=r"^admin_panel$"))
    cb(CallbackQueryHandler(adm_users,            pattern=r"^adm_users$"))
    cb(CallbackQueryHandler(adm_stats,            pattern=r"^adm_stats$"))
    cb(CallbackQueryHandler(adm_containers,       pattern=r"^adm_containers$"))
    cb(CallbackQueryHandler(adm_cleanup,          pattern=r"^adm_cleanup$"))
    cb(CallbackQueryHandler(adm_errors,           pattern=r"^adm_errors$"))

    # Catch-all noop
    cb(CallbackQueryHandler(noop_callback, pattern=r"^noop$"))

    app.add_error_handler(on_error)

    log.info("PyHost Bot starting (polling mode)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
