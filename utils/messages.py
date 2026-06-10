"""All user-facing message templates."""
from __future__ import annotations

WELCOME_MSG = """🚀 *Welcome to PyHost Bot!*

The easiest way to host your Python projects
directly from Telegram.

👤 Your Plan : *{plan}*
📦 Apps      : {apps_used} / {apps_limit} used
⚡ RAM/App   : {ram_mb} MB
🐛 Error Logs: Auto-sent on crash ✅

Get started below 👇"""

FORCE_JOIN_MSG = """⚠️ *Join required*

You must join our channel first to use PyHost Bot.

After joining, tap *✅ I Joined* below."""

RATE_LIMITED_MSG = "⏳ *Slow down!* You're sending requests too fast.\nTry again in {seconds} seconds."

# ── New project flow ────────────────────────────────────────
NEW_PROJECT_STEP1 = """📝 *Let's create your new project!*

*Step 1/4* — Enter your project name:
• Only letters, numbers, hyphens allowed
• Example: `my-flask-app`, `telegram-bot-v2`

Type your project name below 👇"""

INVALID_NAME_MSG = "❌ Invalid name. Only letters, numbers, and hyphens are allowed (3–32 chars)."

NAME_TAKEN_MSG = "❌ You already have a project named `{name}`. Pick a different name."

LIMIT_REACHED_MSG = ("❌ Plan limit reached. You have *{used}/{limit}* projects on the *{plan}* plan.\n\n"
                    "Upgrade your plan to create more.")

NEW_PROJECT_STEP2 = """✅ Project name: `{name}`

*Step 2/4* — Send your code:
Choose how you want to upload 👇"""

UPLOAD_ZIP_PROMPT = "📦 Send your ZIP file now (max 50 MB)."
UPLOAD_PY_PROMPT = "🐍 Send your `.py` file now (max 5 MB)."
UPLOAD_PUBGH_PROMPT = "🐙 Paste your *public GitHub URL* (e.g. `https://github.com/user/repo`)."
UPLOAD_PRIVGH_PROMPT = """🔒 *Private GitHub Repository*

To clone a private repo, you need a GitHub *Personal Access Token (PAT)*.

*Step 1*: Go to github.com/settings/tokens
*Step 2*: Create token with `repo` scope only
*Step 3*: Send token here — it is used *once* and immediately deleted after cloning.

Send your GitHub PAT token 👇"""

PRIVGH_URL_PROMPT = "✅ Token received (will be wiped from memory after clone).\n\nNow send your repo URL 👇"

CLONE_SUCCESS = "✅ Repository cloned!"
CLONE_FAIL    = "❌ Clone failed: {error}"

SCAN_HEAD = "🔍 *Scanning files...*"

SCAN_FAIL = """🚫 *Security scan failed!*

Issue: *{reason}*

Your code was rejected. Please fix the issue and try again."""

DEPLOY_DONE = """🎉 *Project Created Successfully!*

📦 Project : `{name}`
🐍 Python  : {python_version}
🐳 Status  : Ready (Stopped)
📅 Created : {created_at}

⚠️ *Next Steps:*
1. Install your dependencies (📦)
2. Set your ENV variables if needed (🔐)
3. Then hit Start! (▶️)

🐛 Crashes will be auto-reported to you.

Opening your project panel... 👇"""

# ── Project panel ──────────────────────────────────────────
PROJECT_PANEL_MSG = """🗂️ *PROJECT: {name}*
━━━━━━━━━━━━━━━━━━━━━━━━━━
{status_emoji} Status   : *{status}*
🐍 Python   : {python_version}
💾 RAM Used : {ram_mb} / {ram_limit} MB
⚡ CPU      : {cpu_pct}% / {cpu_limit}%
⏱️ Uptime   : {uptime}
🔄 Restarts : {restarts_today} today
📅 Created  : {created_at}

Select an option below:"""

START_OK = """✅ *Project Started!*

▶️ `{name}` is now RUNNING 🟢
🔄 Auto-restart : ON
🐛 Error Report : ON (crashes auto-sent to you)

💡 Tip: Click *Dashboard* to monitor RAM/CPU."""

START_FAIL = """❌ *Start Failed!*

Error:
```
{error}
```

💡 Fix: {hint}"""

STOP_OK    = "⏹️ *Stopped* — `{name}` is no longer running."
RESTART_OK = "🔄 *Restarted* — `{name}` is now running again."

# ── Dashboard / analytics ───────────────────────────────────
DASHBOARD_MSG = """📊 *DASHBOARD — {name}*
━━━━━━━━━━━━━━━━━━━━━━━━━━

{status_emoji} Status    : *{status}*
⏱️ Uptime    : {uptime}
💾 RAM       : {ram_mb} MB / {ram_limit} MB  [{ram_bar}] {ram_pct}%
⚡ CPU       : {cpu_pct}% / {cpu_limit}%      [{cpu_bar}] {cpu_pct}%
📡 Requests  : {requests}
💥 Crashes   : {crashes_today} today
🔄 Restarts  : {restarts_today} today

_Last updated: just now_"""

ANALYTICS_HEAD = """📈 *ANALYTICS — {name}*
━━━━━━━━━━━━━━━━━━━━━━━━━━

📅 *Last {days} Days:*
```
{table}
```

🔥 Peak Day : {peak}
💚 Uptime   : {uptime_pct}%
💥 Crashes  : {total_crashes}"""

# ── Install deps ───────────────────────────────────────────
DEPS_FOUND = """📦 *Dependency Installation*
Project: `{name}`

Your `requirements.txt` was found:
─────────────────────────────
```
{packages}
```
─────────────────────────────
*{count} packages found.*"""

DEPS_NO_FILE = ("ℹ️ No `requirements.txt` found in your project.\n"
                "Add one and redeploy, or use the file manager to upload it.")

# ── Run command ────────────────────────────────────────────
RUNCMD_PROMPT = """✏️ *Edit Run Command*
Project: `{name}`

Current command:
› `{current}`

Send your new run command below.
Examples:
• `python app.py`
• `python bot.py`
• `python -m uvicorn main:app --port 8000`

⚠️ No chained commands (no `; | && ||`)"""

RUNCMD_UPDATED = "✅ *Run command updated!*\nNew command: `{cmd}`\n\n⚠️ Restart your project to apply changes."
RUNCMD_REJECTED = "❌ Rejected. Forbidden characters in run command: `{cmd}`"

# ── ENV setup ──────────────────────────────────────────────
ENV_MENU = """🔐 *Environment Variables*
Project: `{name}`

Current Variables:
━━━━━━━━━━━━━━━━━━
{vars}
━━━━━━━━━━━━━━━━━━
*{count} variables set*"""

ENV_ADD_PROMPT = "Send variable in this format:\n`KEY=VALUE`\n\nExample: `BOT_TOKEN=1234567:ABC...`"
ENV_UPLOAD_PROMPT = "📤 Send your `.env` file directly.\nIt will be parsed and stored securely."
ENV_ADDED = "✅ `{key}` saved (encrypted)."
ENV_DELETED = "🗑️ `{key}` deleted."

# ── Logs ───────────────────────────────────────────────────
LOGS_HEAD = """📋 *LIVE LOGS — {name}*
━━━━━━━━━━━━━━━━━━━━━━━━━━
```
{tail}
```

_Last updated: just now_"""

LOG_SENT = "📎 *Logs sent!*\nFile: `{filename}`\nLines: {lines} | Size: {size}"

# ── Errors / crashes ───────────────────────────────────────
CRASH_NOTIFY = """🚨 *Project Crashed — `{name}`*

💥 Exit Code : {exit_code}
⏱️ Uptime    : {uptime}
🔁 Status    : {restart_status}

💡 *Likely Cause:* {error_type}
   → `{error_line}`

📎 Full error log attached below 👇"""

# ── File manager ───────────────────────────────────────────
FILE_MANAGER_HEAD = """📁 *FILE MANAGER — {name}*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📂 `/{path}`

Tap a file to download it 👇"""

# ── Backup ─────────────────────────────────────────────────
BACKUP_MENU = """💾 *BACKUP & RESTORE — {name}*

Pick an option below:"""
BACKUP_DONE = """✅ *Backup created!*

📦 `{filename}`
💾 Size: {size}"""
BACKUP_LIST_HEAD = "📋 *Saved Backups — {name}*\n"
BACKUP_RESTORE_WARN = """⚠️ *Restore will REPLACE all current project files.*

Are you absolutely sure?
This cannot be undone."""
BACKUP_RESTORE_DONE = "⏳ Restoring backup...\n✅ Restore complete! Project is now Stopped."

# ── Scheduler ──────────────────────────────────────────────
SCHED_MENU = """⏰ *TASK SCHEDULER — {name}*

Active Schedules:
━━━━━━━━━━━━━━━━━
{list}
━━━━━━━━━━━━━━━━━"""
SCHED_ADD_TIME = "Enter time in 24h format:\nExample: `03:00` (for 3 AM), `14:30` (for 2:30 PM)"
SCHED_ADDED = "✅ Scheduled!\n{action} — every day at {time}"

# ── Webhook ────────────────────────────────────────────────
WEBHOOK_FREE = """🌐 *Web App Hosting*
━━━━━━━━━━━━━━━━━━━━

Your Flask/FastAPI app needs a public URL.
This feature requires *PREMIUM* plan."""

WEBHOOK_PREMIUM = """🌐 *WEB APP SETUP — {name}*

Your app's public URL:
🔗 `{url}`

Port: `{port}`"""

WEBHOOK_PORT_PROMPT = "Enter the port your app listens on:\nExample: `5000` (Flask) | `8000` (FastAPI)"
WEBHOOK_PORT_SET = "✅ Port `{port}` set!\nYour app is accessible at:\n🔗 `{url}`"

# ── Delete ─────────────────────────────────────────────────
DELETE_CONFIRM = """⚠️ *DELETE PROJECT*

You are about to permanently delete:
📦 `{name}`

This will:
✖️ Stop the running container
✖️ Delete all project files
✖️ Delete all logs and error reports
✖️ Delete all ENV variables
✖️ Delete all backups
✖️ Remove all schedules

⚠️ *This action CANNOT be undone!*"""

DELETE_DONE = """✅ *Project deleted successfully.*
You can create a new project anytime."""

# ── My projects ────────────────────────────────────────────
MY_PROJECTS_HEAD = "📂 *Your Projects*\nPlan: *{plan}* ({used}/{limit} used) | Page {page}/{total_pages}"

MY_PROJECTS_EMPTY = ("📭 You have no projects yet.\n\n"
                     "Tap *🆕 New Project* to create one!")

# ── Help / support ─────────────────────────────────────────
HELP_MSG = """❓ *PyHost Bot — Help*

*Commands:*
/start — main menu
/newproject — create a new project
/myprojects — list your projects
/admin — admin panel (admins only)
/cancel — abort the current flow

*Buttons in the project panel:*
▶️ Start / ⏹️ Stop / 🔄 Restart your container
📦 Install Deps — runs `pip install -r requirements.txt`
✏️ Edit Run CMD — change the run command
📋 Logs / 📊 Dashboard / 📈 Analytics
🔐 ENV Setup — manage encrypted env vars
📁 File Manager — browse & download files
💾 Backup — create / download / restore zip backups
⏰ Scheduler — daily auto-restart, log clear, stats
🌐 Webhook — public URL for web apps (Premium)
🗑️ Delete — wipe project forever

🐛 On every crash, a `.txt` error report is auto-sent."""

SUPPORT_MSG = "📞 *Support*\n\nContact: @YourSupportHandle\nOr open an issue: github.com/your/repo"
UPGRADE_MSG = """💎 *Upgrade to Premium*

Premium gives you:
• 5 projects (vs 1 free)
• 512 MB RAM per app (vs 256 MB)
• 1.0 CPU per app (vs 0.5)
• 🌐 Web app public URLs (webhook setup)
• Priority support

Contact @YourSupportHandle to upgrade."""

# ── Admin ──────────────────────────────────────────────────
ADMIN_PANEL = """🛡️ *ADMIN PANEL*
━━━━━━━━━━━━━━━━━
📊 *Bot Stats:*
👥 Total Users  : {users}
🐳 Running Apps : {running}
💾 Server RAM   : {ram_used} / {ram_total} GB
⚡ Server CPU   : {cpu_pct}%"""

ADMIN_ONLY = "🚫 This command is for bot admins only."

# ── Cancel / generic ───────────────────────────────────────
CANCELLED_MSG = "❌ Cancelled."
GENERIC_ERROR = "⚠️ Something went wrong. Please try again or contact support."
NOT_FOUND = "❌ Project not found (it may have been deleted)."
