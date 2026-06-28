"""All user-facing message templates — Clean responsive UI (no box-drawing chars that break on some devices)."""
from __future__ import annotations

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WELCOME & AUTH
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

WELCOME_MSG = """\
🚀 *PyHost — Cloud Panel*

👋 *Welcome back!* Your dashboard is ready.

👤 *Plan* — *{plan}*
📦 *Projects* — *{apps_used} / {apps_limit}* used
⚡ *RAM / App* — *{ram_mb} MB*
🛡️ *Crash Log* — Auto-notify ✅

_Choose an action below_ 👇\
"""

FORCE_JOIN_MSG = """\
🔒 *Access Restricted*

You must join our channel to use PyHost.

📢 Tap *Join Channel* below, then confirm.\
"""

RATE_LIMITED_MSG = "⏱️ *Slow down!*  Try again in *{seconds}s*."

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NEW PROJECT FLOW
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NEW_PROJECT_STEP1 = """\
🆕 *New Project — Step 1 of 4*

📝 *Enter a project name:*
• Letters, numbers and hyphens only
• Length: 3–32 characters

💡 _Examples:_ `my-flask-app`  ·  `telegram-bot-v2`

✍️ Type your project name below 👇\
"""

INVALID_NAME_MSG = "⚠️ *Invalid name.* Only letters, numbers and hyphens allowed *(3–32 chars)*."

NAME_TAKEN_MSG = "⚠️ You already have a project named `{name}`. Please choose a different name."

LIMIT_REACHED_MSG = """\
🚫 *Project Limit Reached*

You're using *{used}/{limit}* slots on the *{plan}* plan.

💎 Upgrade to unlock more projects!\
"""

NEW_PROJECT_STEP2 = """\
✅ *Name confirmed:* `{name}`

🆕 *New Project — Step 2 of 4*

📁 *How do you want to upload your code?*\
"""

UPLOAD_ZIP_PROMPT    = "📦 *Send your ZIP file* _(max 50 MB)_ 👇"
UPLOAD_PY_PROMPT     = "🐍 *Send your `.py` file* _(max 5 MB)_ 👇"
UPLOAD_PUBGH_PROMPT  = "🌐 *Paste your public GitHub URL*\n_e.g._ `https://github.com/user/repo`"
UPLOAD_PRIVGH_PROMPT = """\
🔒 *Private GitHub Repository*

To clone a private repo you need a *Personal Access Token (PAT)*.

📋 *Steps:*
*1.* Go to `github.com/settings/tokens`
*2.* Create token with `repo` scope only
*3.* Paste your token below — used *once*, then wiped 🗑️

🔑 Send your GitHub PAT 👇\
"""

PRIVGH_URL_PROMPT = "✅ *Token received* _(wiped after clone)_\n\n🔗 Now send your repo URL 👇"

CLONE_SUCCESS = "✅ *Repository cloned successfully!*"
CLONE_FAIL    = "❌ *Clone failed:* {error}"

SCAN_HEAD = "🔍 *Scanning your files…*"

SCAN_FAIL = """\
🚫 *Security Scan Failed*

⚠️ *Issue:* {reason}

Your code was rejected. Please fix the issue and try again.\
"""

DEPLOY_DONE = """\
🎉 *Project Created!*

📦 *Name* — `{name}`
🐍 *Python* — {python_version}
🐳 *Status* — 🟡 Ready _(stopped)_
📅 *Created* — {created_at}

⚡ *Next Steps:*
*1.* 📦 Install dependencies
*2.* 🔐 Set ENV variables _(if needed)_
*3.* ▶️ Hit Start!

🐛 _Crashes will be auto-reported to you._

_Opening project panel…_ 👇\
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROJECT PANEL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PROJECT_PANEL_MSG = """\
🗂️ *{name}*

{status_emoji} *Status* — {status}
🐍 *Python* — {python_version}
💾 *RAM* — {ram_mb} / {ram_limit} MB
⚡ *CPU* — {cpu_pct}% / {cpu_limit}%
⏱️ *Uptime* — {uptime}
🔄 *Restarts* — {restarts_today} today
📅 *Created* — {created_at}

_Select an action below_ 👇\
"""

START_OK = """\
▶️ *Project Started!*

🟢 `{name}` is now *RUNNING*
🔄 Auto-restart — ON
🐛 Error Report — ON

💡 _Tap Dashboard to monitor RAM / CPU_\
"""

START_FAIL = """\
❌ *Start Failed*

```
{error}
```

💡 *Hint:* {hint}\
"""

STOP_OK    = "⏹️ *Stopped* — `{name}` is no longer running."
RESTART_OK = "🔄 *Restarted* — `{name}` is running again. 🟢"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DASHBOARD & ANALYTICS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DASHBOARD_MSG = """\
📊 *Dashboard — {name}*

{status_emoji} *Status* — {status}
⏱️ *Uptime* — {uptime}
💾 *RAM* — {ram_mb} MB / {ram_limit} MB  `{ram_bar}` *{ram_pct}%*
⚡ *CPU* — {cpu_pct}% / {cpu_limit}%  `{cpu_bar}` *{cpu_pct}%*
📡 *Requests* — {requests}
💥 *Crashes* — {crashes_today} today
🔄 *Restarts* — {restarts_today} today

_🕐 Last updated: just now_\
"""

ANALYTICS_HEAD = """\
📈 *Analytics — {name}*

📅 *Last {days} Days:*
```
{table}
```

🔥 *Peak Day* — {peak}
💚 *Uptime* — {uptime_pct}%
💥 *Crashes* — {total_crashes}\
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# INSTALL DEPS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DEPS_FOUND = """\
📦 *Dependency Installation*

Project: `{name}`

Found `requirements.txt`:
```
{packages}
```
📋 *{count} packages* ready to install.\
"""

DEPS_NO_FILE = """\
ℹ️ *No `requirements.txt` found.*

Add one to your project root, or use the File Manager to upload it.\
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RUN COMMAND
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RUNCMD_PROMPT = """\
✏️ *Edit Run Command*

Project: `{name}`

Current command:
`{current}`

Send your new run command 👇
_Examples:_
• `python app.py`
• `python bot.py`
• `python -m uvicorn main:app --port 8000`

⚠️ _No chained commands_ `(; | && ||)`\
"""

RUNCMD_UPDATED  = "✅ *Run command updated!*\n`{cmd}`\n\n⚠️ _Restart your project to apply changes._"
RUNCMD_REJECTED = "❌ *Rejected.* Forbidden characters in command: `{cmd}`"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ENV SETUP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ENV_MENU = """\
🔐 *Environment Variables*

Project: `{name}`

{vars}

🔒 *{count} variables* stored _(encrypted)_\
"""

ENV_ADD_PROMPT    = "➕ *Add Variable*\n\nSend in format: `KEY=VALUE`\n\n_Example:_ `BOT_TOKEN=1234567:ABC...`"
ENV_UPLOAD_PROMPT = "📤 *Send your `.env` file* — it will be parsed and stored securely."
ENV_ADDED         = "✅ `{key}` saved _(encrypted)_."
ENV_DELETED       = "🗑️ `{key}` deleted."

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOGS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

LOGS_HEAD = """\
📋 *Live Logs — {name}*

```
{tail}
```
_🕐 Last updated: just now_\
"""

LOG_SENT = "📎 *Logs sent!*\nFile: `{filename}` · Lines: {lines} · Size: {size}"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ERRORS / CRASHES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CRASH_NOTIFY = """\
🚨 *Project Crashed!*

📦 *Project* — `{name}`
💥 *Exit Code* — {exit_code}
⏱️ *Uptime* — {uptime}
🔁 *Status* — {restart_status}

💡 *Likely Cause:* {error_type}
`{error_line}`

📎 _Full error log attached below_ 👇\
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FILE MANAGER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FILE_MANAGER_HEAD = """\
📁 *File Manager — {name}*

📂 `/{path}`

_Tap a file to download it_ 👇\
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BACKUP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BACKUP_MENU          = "💾 *Backup & Restore — {name}*\n\n_Choose an option below_ 👇"
BACKUP_DONE          = "✅ *Backup created!*\n\n📦 `{filename}`\n💾 Size: {size}"
BACKUP_LIST_HEAD     = "📋 *Saved Backups — {name}*\n"
BACKUP_RESTORE_WARN  = "⚠️ *Restore will REPLACE all current project files.*\n\nThis cannot be undone. Are you sure?"
BACKUP_RESTORE_DONE  = "⏳ _Restoring backup…_\n✅ *Restore complete!* Project is now stopped."

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SCHEDULER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SCHED_MENU     = "⏰ *Task Scheduler — {name}*\n\n*Active Schedules:*\n{list}"
SCHED_ADD_TIME = "🕐 *Set schedule time* (24h format)\n\n_Examples:_ `03:00` (3 AM)  ·  `14:30` (2:30 PM)"
SCHED_ADDED    = "✅ *Scheduled!*\n{action} — every day at *{time}*"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# WEBHOOK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

WEBHOOK_FREE = """\
🌐 *Web App Hosting*

Host your Flask / FastAPI app with a *public URL*.

🔒 This feature requires *PREMIUM* plan.
💎 Upgrade to unlock it!\
"""

WEBHOOK_PREMIUM = """\
🌐 *Web App Setup — {name}*

🔗 *Your public URL:*
`{url}`

🔌 *Port:* `{port}`\
"""

WEBHOOK_PORT_PROMPT = "🔌 *Enter your app's port:*\n\n_Examples:_ `5000` _(Flask)_  ·  `8000` _(FastAPI)_"
WEBHOOK_PORT_SET    = "✅ *Port `{port}` set!*\n\n🔗 Your app is live at:\n`{url}`"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DELETE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DELETE_CONFIRM = """\
⚠️ *Delete Project*

You are about to *permanently delete:*
📦 `{name}`

This will remove:
✖️ Running container
✖️ All project files
✖️ Logs & error reports
✖️ ENV variables
✖️ Backups & schedules

🚫 *This action CANNOT be undone!*\
"""

DELETE_DONE = "✅ *Project deleted.* You can create a new one anytime."

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MY PROJECTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MY_PROJECTS_HEAD  = "📂 *Your Projects*\n\n🏷️ Plan: *{plan}*  ·  {used}/{limit} used  ·  Page {page}/{total_pages}"
MY_PROJECTS_EMPTY = "📭 *No projects yet.*\n\nTap *🆕 New Project* to deploy your first app!"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HELP & SUPPORT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HELP_MSG = """\
❓ *PyHost — Help & Docs*

📌 *Commands:*
/start — Main menu
/newproject — Create a new project
/myprojects — List your projects
/admin — Admin panel _(admins only)_
/cancel — Abort current action

⚙️ *Project Panel Buttons:*

▶️ Start  ·  ⏹️ Stop  ·  🔄 Restart
📦 Install Deps — `pip install -r requirements.txt`
✏️ Run Command — change the startup command
📋 Logs  ·  📊 Dashboard  ·  📈 Analytics
🔐 ENV Setup — encrypted environment variables
📁 File Manager — browse & download files
💾 Backup — create, download, restore backups
⏰ Scheduler — daily auto-tasks
🌐 Webhook — public URL _(Premium)_
🗑️ Delete — permanently remove project

🐛 _Crash reports are auto-sent on every error._\
"""

SUPPORT_MSG = "📞 *Support*\n\nContact: @YourSupportHandle\nIssues: `github.com/your/repo`"

UPGRADE_MSG = """\
💎 *Upgrade to Premium*

*What you get:*

Feature         Free → Pro
Projects          1  →  5
RAM / App       256  → 512 MB
CPU / App       0.5  → 1.0
Web App URLs     ❌  →  ✅
Priority Support ❌  →  ✅

📩 Contact @YourSupportHandle to upgrade.\
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ADMIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ADMIN_PANEL = """\
🛡️ *Admin Panel*

📊 *Server Stats:*
👥 *Total Users* — {users}
🐳 *Running Apps* — {running}
💾 *Server RAM* — {ram_used} / {ram_total} GB
⚡ *Server CPU* — {cpu_pct}%\
"""

ADMIN_ONLY = "🚫 *Admin only.* You don't have permission to use this."

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GENERIC
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CANCELLED_MSG = "❌ *Cancelled.* Back to square one."
GENERIC_ERROR = "⚠️ *Something went wrong.* Please try again or contact support."
NOT_FOUND     = "❌ *Project not found* — it may have been deleted."
