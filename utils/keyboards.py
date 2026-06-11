"""
All inline keyboards — using PTB 22.7's official `style` parameter.

Telegram Bot API (Bot API 7.10+, PTB 22.7+) supports exactly 3 button styles:
  • 'primary'  → Blue   (main actions)
  • 'success'  → Green  (positive/confirm actions)
  • 'danger'   → Red    (destructive/warning actions)
  • omit style → App default gray/white (neutral/back/cancel)

Note: style only renders on Telegram clients released after February 9, 2026.
      Older clients log "invalid button style specified" — this is harmless
      (buttons still work, just without colour) and is suppressed via api_kwargs.
"""
from __future__ import annotations

from typing import List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


# ────────────────────────────────────────────────────────────
# Button factory
# ────────────────────────────────────────────────────────────
def _btn(text: str,
         callback_data: Optional[str] = None,
         *,
         style: Optional[str] = None,
         url: Optional[str] = None,
         icon_custom_emoji_id: Optional[str] = None) -> InlineKeyboardButton:
    """
    Create an InlineKeyboardButton.

    style must be one of: 'primary' (blue), 'success' (green), 'danger' (red).
    Omit style (None) for the default app style (gray/neutral).

    A URL button cannot have callback_data — only one action type per button.

    FIX: style is passed via api_kwargs to avoid "invalid button style" errors
    on older Telegram clients that don't support Bot API 8.3+ styling.
    Buttons still function normally on all clients — only colour is missing on old ones.
    """
    # URL button — no callback_data, no style (Telegram doesn't support style+url)
    if url is not None:
        return InlineKeyboardButton(text, url=url)

    # Build api_kwargs for style (avoids client-side parse errors on old Telegram versions)
    api_kwargs: dict = {}
    if style is not None:
        api_kwargs["style"] = style
    if icon_custom_emoji_id is not None:
        api_kwargs["icon_custom_emoji_id"] = icon_custom_emoji_id

    if api_kwargs:
        return InlineKeyboardButton(
            text,
            callback_data=callback_data,
            api_kwargs=api_kwargs,
        )
    return InlineKeyboardButton(text, callback_data=callback_data)


def _markup(rows: List[List[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(rows)


# ────────────────────────────────────────────────────────────
# Auth / force-join
# ────────────────────────────────────────────────────────────
def force_join_keyboard(channel_username: str) -> InlineKeyboardMarkup:
    channel = channel_username.lstrip("@")
    return _markup([
        # URL button — no callback_data (Telegram rule: one type only)
        [_btn("📢 Join Channel", url=f"https://t.me/{channel}")],
        # Callback button
        [_btn("✅ I Joined", "auth_check", style="success")],
    ])


# ────────────────────────────────────────────────────────────
# Main menu
# ────────────────────────────────────────────────────────────
def start_menu_keyboard() -> InlineKeyboardMarkup:
    return _markup([
        [_btn("🆕 New Project",  "new_project", style="success"),
         _btn("📂 My Projects",  "my_projects", style="primary")],
        [_btn("📊 Dashboard",    "dashboard",   style="primary"),
         _btn("💎 Upgrade Plan", "upgrade",     style="success")],
        [_btn("❓ Help & Docs",  "help"),
         _btn("📞 Support",      "support")],
    ])


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return _markup([[_btn("🔙 Back to Menu", "main_menu")]])


# ────────────────────────────────────────────────────────────
# New project flow
# ────────────────────────────────────────────────────────────
def cancel_keyboard() -> InlineKeyboardMarkup:
    return _markup([[_btn("❌ Cancel", "cancel_flow", style="danger")]])


def upload_type_keyboard() -> InlineKeyboardMarkup:
    return _markup([
        [_btn("📦 Upload ZIP File",       "upload_zip",    style="primary")],
        [_btn("🐙 Public GitHub URL",     "upload_pubgh",  style="primary")],
        [_btn("🔒 Private GitHub Repo",   "upload_privgh", style="primary")],
        [_btn("🐍 Upload .py File",       "upload_py",     style="primary")],
        [_btn("❌ Cancel",                "cancel_flow",   style="danger")],
    ])


def python_version_keyboard() -> InlineKeyboardMarkup:
    return _markup([
        [_btn("🐍 Python 3.10", "pyver_3.10")],
        [_btn("🐍 Python 3.11", "pyver_3.11")],
        [_btn("🐍 Python 3.12 ⭐ Recommended", "pyver_3.12", style="success")],
    ])


def confirm_cancel_keyboard(confirm_data: str, cancel_data: str = "cancel_flow") -> InlineKeyboardMarkup:
    return _markup([[
        _btn("✅ Confirm", confirm_data, style="success"),
        _btn("❌ Cancel",  cancel_data,  style="danger"),
    ]])


# ────────────────────────────────────────────────────────────
# Project panel
# ────────────────────────────────────────────────────────────
def project_panel_keyboard(project_id: str, is_running: bool) -> InlineKeyboardMarkup:
    pid = project_id
    start_btn = _btn("▶️ Start",  f"start_{pid}",  style="success")
    stop_btn  = _btn("⏹️ Stop",   f"stop_{pid}",   style="danger")

    return _markup([
        [stop_btn if is_running else start_btn,
         _btn("🔄 Restart",        f"restart_{pid}")],
        [_btn("📦 Install Deps",   f"deps_{pid}",     style="primary"),
         _btn("✏️ Edit Run CMD",   f"runcmd_{pid}")],
        [_btn("📋 Live Logs",      f"logs_{pid}",     style="primary"),
         _btn("📊 Dashboard",      f"dash_{pid}",     style="primary")],
        [_btn("📈 Analytics",      f"ana_{pid}",      style="primary"),
         _btn("🔐 ENV Setup",      f"env_{pid}")],
        [_btn("📁 File Manager",   f"files_{pid}"),
         _btn("💾 Backup",         f"backup_{pid}")],
        [_btn("⏰ Scheduler",      f"sched_{pid}"),
         _btn("🌐 Webhook",        f"webhook_{pid}")],
        [_btn("🗑️ Delete",         f"delete_{pid}",  style="danger")],
        [_btn("🔙 Back to Menu",   "main_menu")],
    ])


def back_to_panel_keyboard(project_id: str) -> InlineKeyboardMarkup:
    return _markup([[_btn("🔙 Back to Panel", f"panel_{project_id}")]])


# ────────────────────────────────────────────────────────────
# My projects (paginated)
# ────────────────────────────────────────────────────────────
def my_projects_keyboard(projects: list, page: int, total_pages: int,
                         per_page: int = 5) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    for p in projects:
        emoji = "🟢" if p["status"] == "running" else "🔴"
        label = f"{emoji} {p['name']}  ({p['status']})"
        rows.append([_btn(label, f"panel_{p['project_id']}", style="primary")])

    nav: List[InlineKeyboardButton] = []
    if page > 1:
        nav.append(_btn("◀️ Prev", f"mp_page_{page-1}"))
    nav.append(_btn(f"Page {page}/{total_pages}", "noop"))
    if page < total_pages:
        nav.append(_btn("Next ▶️", f"mp_page_{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([_btn("🆕 New Project", "new_project", style="success"),
                 _btn("🔙 Menu",        "main_menu")])
    return _markup(rows)


# ────────────────────────────────────────────────────────────
# Error report buttons
# ────────────────────────────────────────────────────────────
def error_report_keyboard(project_id: str) -> InlineKeyboardMarkup:
    return _markup([
        [_btn("🔐 Fix ENV",      f"env_{project_id}",  style="primary"),
         _btn("📦 Install Deps", f"deps_{project_id}", style="primary")],
        [_btn("📋 View Logs",    f"logs_{project_id}", style="primary"),
         _btn("⏹️ Stop",         f"stop_{project_id}", style="danger")],
        [_btn("🔙 Back to Panel", f"panel_{project_id}")],
    ])


# ────────────────────────────────────────────────────────────
# ENV setup
# ────────────────────────────────────────────────────────────
def env_menu_keyboard(project_id: str, has_vars: bool) -> InlineKeyboardMarkup:
    rows = [
        [_btn("➕ Add Variable",     f"envadd_{project_id}", style="success")],
        [_btn("📤 Upload .env File", f"envup_{project_id}",  style="primary")],
    ]
    if has_vars:
        rows.append([_btn("✏️ Edit Variable",  f"envedit_{project_id}")])
        rows.append([_btn("🗑️ Delete Variable", f"envdel_{project_id}", style="danger")])
    rows.append([_btn("🔙 Back to Panel", f"panel_{project_id}")])
    return _markup(rows)


def env_keys_keyboard(project_id: str, keys: List[str], action: str) -> InlineKeyboardMarkup:
    """action = 'edit' or 'del'"""
    rows: List[List[InlineKeyboardButton]] = []
    for k in keys:
        cb = f"envk_{action}_{project_id}_{k}"
        style = "danger" if action == "del" else "primary"
        rows.append([_btn(k, cb, style=style)])
    rows.append([_btn("❌ Cancel", f"env_{project_id}", style="danger")])
    return _markup(rows)


# ────────────────────────────────────────────────────────────
# Logs
# ────────────────────────────────────────────────────────────
def logs_keyboard(project_id: str) -> InlineKeyboardMarkup:
    pid = project_id
    return _markup([
        [_btn("🔄 Refresh",         f"logs_{pid}",      style="primary")],
        [_btn("📥 Last 100 Lines",  f"logd_{pid}_100")],
        [_btn("📥 Last 500 Lines",  f"logd_{pid}_500")],
        [_btn("📥 Full Log",        f"logd_{pid}_full")],
        [_btn("🚨 Error Logs Only", f"logd_{pid}_err",  style="danger")],
        [_btn("🔙 Back to Panel",   f"panel_{pid}")],
    ])


# ────────────────────────────────────────────────────────────
# Backup
# ────────────────────────────────────────────────────────────
def backup_menu_keyboard(project_id: str) -> InlineKeyboardMarkup:
    return _markup([
        [_btn("📤 Create Backup Now",   f"bkcreate_{project_id}",  style="success")],
        [_btn("📋 My Backups",          f"bklist_{project_id}",    style="primary")],
        [_btn("📥 Restore from Backup", f"bkrestore_{project_id}")],
        [_btn("🔙 Back to Panel",       f"panel_{project_id}")],
    ])


def backup_list_keyboard(project_id: str, backups: list) -> InlineKeyboardMarkup:
    rows = []
    for b in backups[:10]:
        bid = b["backup_id"]
        size_mb = b["size_bytes"] / (1024 * 1024)
        label = f"📦 {b['created_at'].strftime('%d%b-%H%M')} — {size_mb:.1f} MB"
        rows.append([
            _btn(f"📥 {label}",  f"bkdl_{bid}",  style="primary"),
            _btn("🗑️",           f"bkrm_{bid}",  style="danger"),
        ])
    rows.append([_btn("🔙 Back", f"backup_{project_id}")])
    return _markup(rows)


# ────────────────────────────────────────────────────────────
# Scheduler
# ────────────────────────────────────────────────────────────
def scheduler_menu_keyboard(project_id: str, has_schedules: bool) -> InlineKeyboardMarkup:
    rows = [[_btn("➕ Add Schedule", f"schadd_{project_id}", style="success")]]
    if has_schedules:
        rows.append([_btn("🗑️ Remove Schedule", f"schrm_{project_id}", style="danger")])
    rows.append([_btn("🔙 Back to Panel", f"panel_{project_id}")])
    return _markup(rows)


def scheduler_action_keyboard(project_id: str) -> InlineKeyboardMarkup:
    return _markup([
        [_btn("🔄 Auto Restart",       f"schact_{project_id}_restart",   style="primary")],
        [_btn("🧹 Clear Logs",         f"schact_{project_id}_clearlogs")],
        [_btn("📊 Daily Stats Report", f"schact_{project_id}_stats",     style="primary")],
        [_btn("❌ Cancel",             f"sched_{project_id}",            style="danger")],
    ])


# ────────────────────────────────────────────────────────────
# Webhook
# ────────────────────────────────────────────────────────────
def webhook_keyboard(project_id: str, is_premium: bool) -> InlineKeyboardMarkup:
    if not is_premium:
        return _markup([
            [_btn("💎 Upgrade to Premium", "upgrade",          style="success")],
            [_btn("🔙 Back to Panel",       f"panel_{project_id}")],
        ])
    return _markup([
        [_btn("🔌 Set App Port",   f"whport_{project_id}",  style="primary")],
        [_btn("🔄 Regenerate URL", f"whregen_{project_id}")],
        [_btn("🔙 Back to Panel",  f"panel_{project_id}")],
    ])


# ────────────────────────────────────────────────────────────
# Delete confirm
# ────────────────────────────────────────────────────────────
def delete_confirm_keyboard(project_id: str) -> InlineKeyboardMarkup:
    return _markup([
        [_btn("🗑️ Yes, Delete Forever", f"delyes_{project_id}", style="danger")],
        [_btn("❌ Cancel",              f"panel_{project_id}",  style="success")],
    ])


# ────────────────────────────────────────────────────────────
# Admin
# ────────────────────────────────────────────────────────────
def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return _markup([
        [_btn("👥 All Users",         "adm_users",      style="primary"),
         _btn("📊 Server Stats",      "adm_stats",      style="primary")],
        [_btn("⭐ Upgrade User",       "adm_upgrade",    style="success"),
         _btn("🚫 Ban User",           "adm_ban",        style="danger")],
        [_btn("🔓 Unban User",         "adm_unban",      style="success"),
         _btn("📢 Broadcast",          "adm_broadcast",  style="primary")],
        [_btn("🐳 All Containers",    "adm_containers", style="primary"),
         _btn("🧹 Cleanup Dead",       "adm_cleanup",    style="danger")],
        [_btn("📋 All Error Reports",  "adm_errors",     style="primary")],
        [_btn("🔙 Exit", "main_menu")],
    ])


def admin_broadcast_type_keyboard() -> InlineKeyboardMarkup:
    return _markup([
        [_btn("📝 Text Only",        "bcast_text",  style="primary")],
        [_btn("🖼️ Image + Caption", "bcast_image", style="primary")],
        [_btn("❌ Cancel", "admin_panel",           style="danger")],
    ])


# ────────────────────────────────────────────────────────────
# Install deps
# ────────────────────────────────────────────────────────────
def install_deps_keyboard(project_id: str) -> InlineKeyboardMarkup:
    return _markup([
        [_btn("⚡ Install Now", f"depsgo_{project_id}", style="success")],
        [_btn("❌ Cancel",      f"panel_{project_id}",  style="danger")],
    ])


# ────────────────────────────────────────────────────────────
# Start-fail mini keyboard
# ────────────────────────────────────────────────────────────
def start_fail_keyboard(project_id: str) -> InlineKeyboardMarkup:
    return _markup([
        [_btn("📦 Install Deps", f"deps_{project_id}", style="primary"),
         _btn("📋 View Logs",    f"logs_{project_id}", style="primary")],
        [_btn("🔙 Panel", f"panel_{project_id}")],
    ])


# ────────────────────────────────────────────────────────────
# File manager
# ────────────────────────────────────────────────────────────
def file_manager_keyboard(project_id: str, entries: list, cur_rel: str = "") -> InlineKeyboardMarkup:
    """entries: list of dicts {name, is_dir, rel_path}"""
    rows = []
    for e in entries[:30]:
        icon = "📁" if e["is_dir"] else "📄"
        cb = (f"fmcd_{project_id}_{e['rel_path']}"
              if e["is_dir"]
              else f"fmget_{project_id}_{e['rel_path']}")
        rows.append([_btn(f"{icon} {e['name']}", cb,
                          style=None if e["is_dir"] else "primary")])
    if cur_rel:
        parent = "/".join(cur_rel.rstrip("/").split("/")[:-1])
        rows.append([_btn("⬆️ Up one folder", f"fmcd_{project_id}_{parent}")])
    rows.append([_btn("🔙 Back to Panel", f"panel_{project_id}")])
    return _markup(rows)
