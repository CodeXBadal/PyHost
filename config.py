"""
PyHost Bot — central configuration.
"""
from __future__ import annotations

import os
from typing import Dict, List

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
ADMIN_IDS: List[int] = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
FORCE_JOIN_CHANNEL: str = os.getenv("FORCE_JOIN_CHANNEL", "").strip()

MONGO_URI: str = os.getenv("MONGO_URI", "")
MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "")

ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")

PLAN_LIMITS: Dict[str, Dict[str, float]] = {
    "free":    {"projects": 1, "ram_mb": 256, "cpu": 0.5},
    "premium": {"projects": 5, "ram_mb": 512, "cpu": 1.0},
}

ERROR_LOG_MAX_SIZE_KB: int = 500
AUTO_RESTART_MAX_ATTEMPTS: int = 5
AUTO_RESTART_COOLDOWN_SEC: int = 30

CLEANUP_TEMP_EVERY_MIN: int = 60
RESOURCE_POLL_EVERY_SEC: int = 30

# ── Log rotation ────────────────────────────────────────────
LOG_ROTATE_MAX_MB: int = 10        # rotate .pyhost.log when > 10 MB
LOG_ROTATE_KEEP_FILES: int = 3     # keep 3 rotated files max

# ── Resource alert thresholds ────────────────────────────────
RESOURCE_ALERT_RAM_PCT: float = 90.0   # alert when RAM > 90% of limit
RESOURCE_ALERT_CPU_PCT: float = 95.0   # alert when CPU > 95% sustained
RESOURCE_ALERT_COOLDOWN_SEC: int = 300 # minimum seconds between alerts per project

ALLOWED_FILE_EXTENSIONS = {
    # Code & config
    ".py", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".env",
    # Docs & text
    ".md", ".rst", ".txt",
    # Web (for Flask/FastAPI projects)
    ".html", ".css", ".js",
    # Data
    ".csv", ".xml",
    # Shell scripts (allowed but scanned)
    ".sh",
}
MAX_PROJECT_SIZE_MB: int = 50
MAX_SINGLE_FILE_MB: int = 5

DANGER_PATTERNS = [
    "os.system",
    "os.popen",
    "__import__('os')",
    '__import__("os")',
    "eval(",
    "exec(",
    "compile(",
    "rm -rf",
    "chmod 777",
    ":(){:|:&};:",
    "subprocess.Popen",   # HARD FAIL — see _HARD_FAIL_PATTERNS in core/security.py
    "subprocess.run",     # HARD FAIL — see _HARD_FAIL_PATTERNS in core/security.py
    "subprocess.call",    # HARD FAIL — see _HARD_FAIL_PATTERNS in core/security.py
    "ctypes",             # HARD FAIL — see _HARD_FAIL_PATTERNS in core/security.py
    "socket.socket(socket.AF_INET, socket.SOCK_RAW",
]

# Blocked characters/sequences in run commands
RUN_CMD_BLOCK_CHARS = [";", "|", "&&", "||", "`", "$(", ">", "<", "\\"]

ERROR_HINTS: Dict[str, str] = {
    "KeyError":                "ENV variable missing. Go to 🔐 ENV Setup.",
    "ModuleNotFoundError":     "Package not installed. Use 📦 Install Deps.",
    "ImportError":             "Import failed. Check your dependencies (📦 Install Deps).",
    "ConnectionRefusedError":  "Can't connect to external service. Check your API URL.",
    "PermissionError":         "File permission issue. Check your file paths.",
    "MemoryError":             "RAM limit exceeded. Reduce your data usage or upgrade plan.",
    "SyntaxError":             "Python syntax error in your code. Fix and redeploy.",
    "TimeoutError":            "Operation timed out. Check external API calls.",
    "FileNotFoundError":       "File not found. Check your file paths.",
    "json.JSONDecodeError":    "Invalid JSON. Check your config or API response.",
    "JSONDecodeError":         "Invalid JSON. Check your config or API response.",
    "NameError":               "Undefined variable. Did you import everything you use?",
    "TypeError":               "Type mismatch — inspect the traceback line carefully.",
    "ValueError":              "Bad value passed to a function. Validate your inputs.",
}

# BUG-046: align available Python versions with what python-telegram-bot
# 22.7, motor 3.6 and psutil 5.9.8 actually have wheels for.  3.13 is
# included now that PTB and motor both publish wheels; 3.14 wheels are
# not yet universally available so it is intentionally excluded.
PYTHON_IMAGES = {
    "3.10": "python:3.10-slim",
    "3.11": "python:3.11-slim",
    "3.12": "python:3.12-slim",
    "3.13": "python:3.13-slim",
}
DEFAULT_PYTHON_VERSION = "3.12"

CONTAINER_LABEL_PREFIX = "pyhost"

# ── Global rate limit (all actions) ─────────────────────────
RATE_LIMIT_REQUESTS_PER_MIN: int = 30
RATE_LIMIT_WINDOW_SEC: int = 60

# ── Per-action cooldowns (seconds) ───────────────────────────
ACTION_COOLDOWNS: Dict[str, int] = {
    "deploy":   30,    # new project deploy
    "start":    5,     # start project
    "restart":  10,    # restart project
    "install":  60,    # install dependencies
    "backup":   30,    # create backup
    "restore":  30,    # restore backup
    "runcmd":   5,     # change run command
}

PUBLIC_DOMAIN: str = os.getenv("PUBLIC_DOMAIN", "https://pyhost.example.com").rstrip("/")
NGINX_SITES_DIR: str = os.getenv("NGINX_SITES_DIR", "/etc/nginx/sites-enabled")
HEALTHCHECK_HOST: str = os.getenv("HEALTHCHECK_HOST", "127.0.0.1")
HEALTHCHECK_PORT: int = int(os.getenv("HEALTHCHECK_PORT", "8081"))

USER_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "user_data"))
TEMP_DIR     = os.path.join(USER_DATA_DIR, "temp")
BACKUP_DIR   = os.path.join(USER_DATA_DIR, "backups")
ERRLOG_DIR   = os.path.join(USER_DATA_DIR, "error_logs")
PROJECTS_DIR = os.path.join(USER_DATA_DIR, "projects")

for _d in (TEMP_DIR, BACKUP_DIR, ERRLOG_DIR, PROJECTS_DIR):
    os.makedirs(_d, exist_ok=True)

# BUG-013: the banner is now searched at the canonical name AND the legacy
# double-extension name (welcome_banner.jpg.jpg) that some uploads create
# under Windows.  Whichever exists on disk wins.
_BANNER_DIR = os.path.join(os.path.dirname(__file__), "assets")
_BANNER_CANDIDATES = ("welcome_banner.jpg", "welcome_banner.png",
                       "welcome_banner.jpg.jpg")
_banner_path = os.path.join(_BANNER_DIR, _BANNER_CANDIDATES[0])
for _candidate in _BANNER_CANDIDATES:
    _p = os.path.join(_BANNER_DIR, _candidate)
    if os.path.isfile(_p):
        _banner_path = _p
        break
WELCOME_BANNER_PATH = _banner_path

CUSTOM_EMOJI_FIRE  = "5368324170671202286"
CUSTOM_EMOJI_STAR  = "5310169226856644648"
CUSTOM_EMOJI_HEART = "5285430309720966085"
BOT_HAS_PREMIUM = os.getenv("BOT_HAS_PREMIUM", "false").lower() == "true"
