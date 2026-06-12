"""
All inline keyboards — PTB 22.7 style parameter via api_kwargs.

Colour guide used consistently:
  success  (green)  → start, confirm, add, create, install, join, upgrade
  primary  (blue)   → navigate, view, refresh, download, settings
  danger   (red)    → stop, delete, remove, ban, cancel destructive actions
  (none)            → neutral: back, cancel non-destructive, info-only
"""
from __future__ import annotations

from typing import List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


# ── Button factory ─────────────────────────────────────────
def _btn(text: str,
         callback_data: Optional[str] = None,
         *,
         style: Optional[str] = None,
         url: Optional[str] = None) -> InlineKeyboardButton:
    """
    Create an InlineKeyboardButton.

    style must be 'primary' (blue), 'success' (green), or 'danger' (red).
    None = default app style (gray).

    FIX: style passed via api_kwargs to avoid "invalid button style"
    errors on Telegram clients older than Feb 9 2026.
    Buttons still work on all clients; colour is missing only on old ones.
    """
    if url is not None:
        return InlineKeyboardButton(text, url=url)
    if style is not None:
        return InlineKeyboardButton(text, callback_data=callback_data,
                                    api_kwargs={"style": style})
    return InlineKeyboardButton(text, callback_data=callback_data)


def _kb(rows: List[List[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(rows)

# Backwards-compat alias — handlers import _markup directly
_markup = _kb


# ── Force-join / Auth ──────────────────────────────────────
def force_join_keyboard(channel_username: str) -> InlineKeyboardMarkup:
    ch = channel_username.lstrip("@")
    return _kb([
        [_btn("📢 Join Channel", url=f"https://t.me/{ch}")],
        [_btn("✅ I've Joined", "auth_check", style="success")],
    ])


# ── Main menu ──────────────────────────────────────────────
def start_menu_keyboard() -> InlineKeyboardMarkup:
    return _kb([
        [_btn("🆕 New Project",  "new_project", style="success"),
         _btn("📂 My Projects",  "my_projects", style="primary")],
        [_btn("📊 Dashboard",    "dashboard",   style="primary"),
         _btn("💎 Upgrade Plan", "upgrade",     style="success")],
        [_btn("❓ Help & Docs",  "help",        style="primary"),
         _btn("📞 Support",      "support",     style="primary")],
    ])


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return _kb([[_btn("🔙 Back to Menu", "main_menu")]])


# ── New project flow ───────────────────────────────────────
def cancel_keyboard() -> InlineKeyboardMarkup:
    return _kb([[_btn("❌ Cancel", "cancel_flow", style="danger")]])


def upload_type_keyboard() -> InlineKeyboardMarkup:
    return _kb([
        [_btn("📦 Upload ZIP File",       "upload_zip",    style="primary")],
        [_btn("🐍 Upload .py File",       "upload_py",     style="primary")],
        [_btn("🐙 Public GitHub URL",     "upload_pubgh",  style="primary")],
        [_btn("🔒 Private GitHub Repo",   "upload_privgh", style="primary")],
        [_btn("❌ Cancel",                "cancel_flow",   style="danger")],
    ])


def python_version_keyboard() -> InlineKeyboardMarkup:
    return _kb([
        [_btn("🐍 Python 3.10", "pyver_3.10", style="primary")],
        [_btn("🐍 Python 3.11", "pyver_3.11", style="primary")],
        [_btn("🐍 Python 3.12  ⭐ Recommended", "pyver_3.12", style="success")],
        [_btn("❌ Cancel", "cancel_flow", style="danger")],
    ])


def confirm_cancel_keyboard(confirm_data: str,
                             cancel_data: str = "cancel_flow") -> InlineKeyboardMarkup:
    return _kb([[
        _btn("✅ Confirm", confirm_data, style="success"),
        _btn("❌ Cancel",  cancel_data,  style="danger"),
    ]])


# ── Project panel ──────────────────────────────────────────
def project_panel_keyboard(project_id: str, is_running: bool) -> InlineKeyboardMarkup:
    pid = project_id
    run_btn  = (_btn("⏹️ Stop",    f"stop_{pid}",    style="danger")
                if is_running else
                _btn("▶️ Start",   f"start_{pid}",   style="success"))
    return _kb([
        [run_btn,
         _btn("🔄 Restart",        f"restart_{pid}",  style="primary")],
        [_btn("📦 Install Deps",   f"deps_{pid}",     style="success"),
         _btn("✏️ Run Command",    f"runcmd_{pid}",   style="primary")],
        [_btn("📋 Live Logs",      f"logs_{pid}",     style="primary"),
         _btn("📊 Dashboard",      f"dash_{pid}",     style="primary")],
        [_btn("📈 Analytics",      f"ana_{pid}",      style="primary"),
         _btn("🔐 ENV Setup",      f"env_{pid}",      style="primary")],
        [_btn("📁 File Manager",   f"files_{pid}",    style="primary"),
         _btn("💾 Backup",         f"backup_{pid}",   style="primary")],
        [_btn("⏰ Scheduler",      f"sched_{pid}",    style="primary"),
         _btn("🌐 Webhook",        f"webhook_{pid}",  style="primary")],
        [_btn("🗑️ Delete Project", f"delete_{pid}",  style="danger")],
        [_btn("🔙 Back to Menu",   "main_menu")],
    ])


def back_to_panel_keyboard(project_id: str) -> InlineKeyboardMarkup:
    return _kb([[_btn("🔙 Back to Panel", f"panel_{project_id}", style="primary")]])


# ── My Projects (paginated) ────────────────────────────────
def my_projects_keyboard(projects: list, page: int, total_pages: int,
                          per_page: int = 5) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    for p in projects:
        emoji = "🟢" if p["status"] == "running" else "🔴"
        label = f"{emoji} {p['name']}  ({p['status']})"
        rows.append([_btn(label, f"panel_{p['project_id']}", style="primary")])

    nav: List[InlineKeyboardButton] = []
    if page > 1:
        nav.append(_btn("◀️ Prev", f"mp_page_{page-1}", style="primary"))
    nav.append(_btn(f"📄 {page}/{total_pages}", "noop"))
    if page < total_pages:
        nav.append(_btn("Next ▶️", f"mp_page_{page+1}", style="primary"))
    if nav:
        rows.append(nav)

    rows.append([_btn("🆕 New Project", "new_project", style="success"),
                 _btn("🔙 Menu",        "main_menu")])
    return _kb(rows)


# ── Error report ───────────────────────────────────────────
def error_report_keyboard(project_id: str) -> InlineKeyboardMarkup:
    return _kb([
        [_btn("🔐 Fix ENV",      f"env_{project_id}",  style="primary"),
         _btn("📦 Install Deps", f"deps_{project_id}", style="success")],
        [_btn("📋 View Logs",    f"logs_{project_id}", style="primary"),
         _btn("⏹️ Stop",         f"stop_{project_id}", style="danger")],
        [_btn("🔙 Back to Panel", f"panel_{project_id}", style="primary")],
    ])


# ── Start-fail mini keyboard ───────────────────────────────
def start_fail_keyboard(project_id: str) -> InlineKeyboardMarkup:
    return _kb([
        [_btn("📦 Install Deps", f"deps_{project_id}", style="success"),
         _btn("📋 View Logs",    f"logs_{project_id}", style="primary")],
        [_btn("🔐 Fix ENV",      f"env_{project_id}",  style="primary")],
        [_btn("🔙 Panel",        f"panel_{project_id}", style="primary")],
    ])


# ── ENV setup ──────────────────────────────────────────────
def env_menu_keyboard(project_id: str, has_vars: bool) -> InlineKeyboardMarkup:
    rows = [
        [_btn("➕ Add Variable",     f"envadd_{project_id}", style="success")],
        [_btn("📤 Upload .env File", f"envup_{project_id}",  style="primary")],
    ]
    if has_vars:
        rows.append([_btn("✏️ Edit Variable",   f"envedit_{project_id}", style="primary")])
        rows.append([_btn("🗑️ Delete Variable", f"envdel_{project_id}", style="danger")])
    rows.append([_btn("🔙 Back to Panel", f"panel_{project_id}", style="primary")])
    return _kb(rows)


def env_keys_keyboard(project_id: str, keys: List[str],
                       action: str) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    for k in keys:
        cb    = f"envk_{action}_{project_id}_{k}"
        style = "danger" if action == "del" else "primary"
        rows.append([_btn(k, cb, style=style)])
    rows.append([_btn("❌ Cancel", f"env_{project_id}", style="danger")])
    return _kb(rows)


# ── Install deps ───────────────────────────────────────────
def install_deps_keyboard(project_id: str) -> InlineKeyboardMarkup:
    return _kb([
        [_btn("⚡ Install Now", f"depsgo_{project_id}", style="success")],
        [_btn("❌ Cancel",      f"panel_{project_id}",  style="danger")],
    ])


# ── Logs ───────────────────────────────────────────────────
def logs_keyboard(project_id: str) -> InlineKeyboardMarkup:
    pid = project_id
    return _kb([
        [_btn("🔄 Refresh",          f"logs_{pid}",      style="primary")],
        [_btn("📥 Last 100 Lines",   f"logd_{pid}_100",  style="primary"),
         _btn("📥 Last 500 Lines",   f"logd_{pid}_500",  style="primary")],
        [_btn("📥 Full Log",         f"logd_{pid}_full", style="primary"),
         _btn("🚨 Errors Only",      f"logd_{pid}_err",  style="danger")],
        [_btn("🔙 Back to Panel",    f"panel_{pid}",     style="primary")],
    ])


# ── Backup ─────────────────────────────────────────────────
def backup_menu_keyboard(project_id: str) -> InlineKeyboardMarkup:
    return _kb([
        [_btn("📤 Create Backup Now",   f"bkcreate_{project_id}",  style="success")],
        [_btn("📋 My Backups",          f"bklist_{project_id}",    style="primary")],
        [_btn("📥 Restore from Backup", f"bkrestore_{project_id}", style="primary")],
        [_btn("🔙 Back to Panel",       f"panel_{project_id}",     style="primary")],
    ])


def backup_list_keyboard(project_id: str, backups: list) -> InlineKeyboardMarkup:
    rows = []
    for b in backups[:10]:
        bid     = b["backup_id"]
        size_mb = b["size_bytes"] / (1024 * 1024)
        label   = f"📦 {b['created_at'].strftime('%d%b-%H%M')} — {size_mb:.1f} MB"
        rows.append([
            _btn(label,  f"bkdl_{bid}",  style="primary"),
            _btn("🗑️",   f"bkrm_{bid}",  style="danger"),
        ])
    rows.append([_btn("🔙 Back", f"backup_{project_id}", style="primary")])
    return _kb(rows)


# ── Scheduler ──────────────────────────────────────────────
def scheduler_menu_keyboard(project_id: str,
                              has_schedules: bool) -> InlineKeyboardMarkup:
    rows = [[_btn("➕ Add Schedule", f"schadd_{project_id}", style="success")]]
    if has_schedules:
        rows.append([_btn("🗑️ Remove Schedule", f"schrm_{project_id}", style="danger")])
    rows.append([_btn("🔙 Back to Panel", f"panel_{project_id}", style="primary")])
    return _kb(rows)


def scheduler_action_keyboard(project_id: str) -> InlineKeyboardMarkup:
    return _kb([
        [_btn("🔄 Auto Restart",       f"schact_{project_id}_restart",   style="primary")],
        [_btn("🧹 Clear Logs",         f"schact_{project_id}_clearlogs",  style="primary")],
        [_btn("📊 Daily Stats Report", f"schact_{project_id}_stats",      style="primary")],
        [_btn("❌ Cancel",             f"sched_{project_id}",             style="danger")],
    ])


# ── Webhook ────────────────────────────────────────────────
def webhook_keyboard(project_id: str, is_premium: bool) -> InlineKeyboardMarkup:
    if not is_premium:
        return _kb([
            [_btn("💎 Upgrade to Premium", "upgrade",          style="success")],
            [_btn("🔙 Back to Panel",      f"panel_{project_id}", style="primary")],
        ])
    return _kb([
        [_btn("🔌 Set App Port",   f"whport_{project_id}",  style="primary")],
        [_btn("🔄 Regenerate URL", f"whregen_{project_id}", style="primary")],
        [_btn("🔙 Back to Panel",  f"panel_{project_id}",   style="primary")],
    ])


# ── Delete confirm ─────────────────────────────────────────
def delete_confirm_keyboard(project_id: str) -> InlineKeyboardMarkup:
    return _kb([
        [_btn("🗑️ Yes, Delete Forever", f"delyes_{project_id}", style="danger")],
        [_btn("❌ No, Keep It",         f"panel_{project_id}",  style="success")],
    ])


# ── Run command ────────────────────────────────────────────
def run_command_keyboard(project_id: str) -> InlineKeyboardMarkup:
    return _kb([
        [_btn("✅ Save Command",  f"runcmd_save_{project_id}", style="success")],
        [_btn("🔙 Cancel",       f"panel_{project_id}",       style="danger")],
    ])


# ── File manager ───────────────────────────────────────────
def file_manager_keyboard(project_id: str, entries: list,
                           cur_rel: str = "") -> InlineKeyboardMarkup:
    rows = []
    for e in entries[:25]:
        icon = "📁" if e["is_dir"] else "📄"
        cb   = (f"fmcd_{project_id}_{e['rel_path']}"
                if e["is_dir"]
                else f"fmget_{project_id}_{e['rel_path']}")
        rows.append([_btn(f"{icon} {e['name']}", cb,
                          style="primary" if not e["is_dir"] else None)])
    if cur_rel:
        parent = "/".join(cur_rel.rstrip("/").split("/")[:-1])
        rows.append([_btn("⬆️ Up one folder", f"fmcd_{project_id}_{parent}", style="primary")])
    rows.append([_btn("🔙 Back to Panel", f"panel_{project_id}", style="primary")])
    return _kb(rows)


# ── Admin panel ────────────────────────────────────────────
def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return _kb([
        [_btn("👥 All Users",          "adm_users",      style="primary"),
         _btn("📊 Server Stats",       "adm_stats",      style="primary")],
        [_btn("⭐ Upgrade User",        "adm_upgrade",    style="success"),
         _btn("🚫 Ban User",            "adm_ban",        style="danger")],
        [_btn("🔓 Unban User",          "adm_unban",      style="success"),
         _btn("📢 Broadcast",           "adm_broadcast",  style="primary")],
        [_btn("🐳 All Processes",       "adm_containers", style="primary"),
         _btn("🧹 Cleanup Dead",        "adm_cleanup",    style="danger")],
        [_btn("📋 All Error Reports",   "adm_errors",     style="primary")],
        [_btn("🔙 Exit Admin", "main_menu", style="danger")],
    ])


def admin_broadcast_type_keyboard() -> InlineKeyboardMarkup:
    return _kb([
        [_btn("📝 Text Only",        "bcast_text",  style="primary")],
        [_btn("🖼️ Image + Caption", "bcast_image", style="primary")],
        [_btn("❌ Cancel", "admin_panel",           style="danger")],
    ])


def admin_user_actions_keyboard(target_user_id: int) -> InlineKeyboardMarkup:
    uid = target_user_id
    return _kb([
        [_btn("⭐ Upgrade to Premium", f"adm_upguser_{uid}", style="success"),
         _btn("🚫 Ban",               f"adm_banuser_{uid}", style="danger")],
        [_btn("🔓 Unban",             f"adm_unban_{uid}",   style="success"),
         _btn("📊 View Projects",     f"adm_projs_{uid}",   style="primary")],
        [_btn("🔙 Back", "adm_users", style="primary")],
    ])


# ── Upgrade ────────────────────────────────────────────────
def upgrade_keyboard() -> InlineKeyboardMarkup:
    return _kb([
        [_btn("💎 Get Premium", "upgrade_pay", style="success")],
        [_btn("🔙 Back to Menu", "main_menu")],
    ])


# ── Dashboard ──────────────────────────────────────────────
def dashboard_keyboard(project_id: str) -> InlineKeyboardMarkup:
    return _kb([
        [_btn("🔄 Refresh Stats",  f"dash_{project_id}",    style="primary")],
        [_btn("📋 View Logs",      f"logs_{project_id}",    style="primary"),
         _btn("📈 Analytics",      f"ana_{project_id}",     style="primary")],
        [_btn("🔙 Back to Panel",  f"panel_{project_id}",   style="primary")],
    ])


# ── Analytics ──────────────────────────────────────────────
def analytics_keyboard(project_id: str) -> InlineKeyboardMarkup:
    return _kb([
        [_btn("📅 Last 24 hours", f"ana_{project_id}_24h",  style="primary"),
         _btn("📅 Last 7 days",   f"ana_{project_id}_7d",   style="primary")],
        [_btn("📅 Last 30 days",  f"ana_{project_id}_30d",  style="primary")],
        [_btn("🔙 Back to Panel", f"panel_{project_id}",    style="primary")],
    ])
