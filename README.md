# 🚀 PyHost Bot

Production-grade Telegram bot for hosting Python projects in isolated Docker containers, controlled entirely from chat.

## Features

- 🆕 Create projects from ZIP, public GitHub, **private GitHub (PAT, deleted-after-clone)**, or single `.py` file
- 🐳 Per-project Docker container — `python:3.10/3.11/3.12-slim`, 256 MB RAM, 0.5 CPU, no privileges, no caps
- 🛡️ 7-step security scanner (file types, malware patterns, dangerous code, run-cmd injection, secrets, structure)
- 📊 Live dashboard (RAM / CPU / uptime / crashes / requests) and 7-day analytics
- 🚨 **Auto crash report** — `.txt` file with traceback + smart hint sent to user instantly
- 📦 Install Deps with live per-package animation
- 📋 Logs viewer + 4 download options (100 / 500 / full / errors-only)
- 🔐 ENV-var manager (manual or `.env` upload) — values **AES-256 encrypted at rest** (Fernet)
- 📁 File manager — browse + download project files
- 💾 ZIP backup / restore
- ⏰ Scheduler — daily auto-restart, log clear, daily-stats report
- 🌐 Webhook setup (Premium) — auto-generated Nginx proxy & public URL
- 🛡️ Admin panel — users, broadcasts, container ops, error reports, ban/unban/upgrade
- 🔒 Force-join channel + Redis rate-limit (30 req/min)
- 🐍 Built on `python-telegram-bot 22.7`, Motor (Mongo), Redis, APScheduler

## Quick Start

```bash
cp .env.example .env
# fill in BOT_TOKEN, ADMIN_IDS, FORCE_JOIN_CHANNEL, ENCRYPTION_KEY

# Generate an ENCRYPTION_KEY:
python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"

# Then:
docker compose up --build -d
docker compose logs -f bot
```

Or without Docker:

```bash
pip install -r requirements.txt
python main.py
```

> The bot needs access to the host Docker socket — it manages **sibling** containers for each user project. `docker-compose.yml` mounts `/var/run/docker.sock` automatically.

## Notes on PTB 22.7 styled buttons

The Telegram Bot API recently added `style` (`success` / `danger` / `primary`) and `icon_custom_emoji_id` on `InlineKeyboardButton`. As of mid-2025, `python-telegram-bot` had not yet officially exposed these. `utils/keyboards._btn()` therefore **tries to pass them and falls back gracefully** if the installed PTB version rejects them — so the bot runs today and automatically picks up styled buttons the moment PTB ships support.

## Project Layout

See the structure in the repo. All modules are async, type-hinted, and documented.

## License

MIT — adapt freely.
