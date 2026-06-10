"""
PyHost Bot — central configuration.

All tokens & limits live here. Reads from environment via python-dotenv.
"""
from __future__ import annotations

import os
from typing import Dict, List

from dotenv import load_dotenv

load_dotenv()

# ────────────────────────────────────────────────────────────
# Bot core
# ────────────────────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
ADMIN_IDS: List[int] = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
FORCE_JOIN_CHANNEL: str = os.getenv("FORCE_JOIN_CHANNEL", "").strip()

# ────────────────────────────────────────────────────────────
# Infra
# ────────────────────────────────────────────────────────────
MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "pyhost")

# 32-byte Fernet key for ENV var encryption (AES-256-equivalent under the hood)
ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")

# ────────────────────────────────────────────────────────────
# Plans
# ────────────────────────────────────────────────────────────
PLAN_LIMITS: Dict[str, Dict[str, float]] = {
    "free":    {"projects": 1, "ram_mb": 256, "cpu": 0.5},
    "premium": {"projects": 5, "ram_mb": 512, "cpu": 1.0},
}

# ────────────────────────────────────────────────────────────
# Error reporting
# ────────────────────────────────────────────────────────────
ERROR_LOG_MAX_SIZE_KB: int = 500
AUTO_RESTART_MAX_ATTEMPTS: int = 5
AUTO_RESTART_COOLDOWN_SEC: int = 30

# ────────────────────────────────────────────────────────────
# Cleanup & polling
# ────────────────────────────────────────────────────────────
CLEANUP_TEMP_EVERY_MIN: int = 60
RESOURCE_POLL_EVERY_SEC: int = 30

# ────────────────────────────────────────────────────────────
# Security
# ────────────────────────────────────────────────────────────
ALLOWED_FILE_EXTENSIONS = {
    ".py", ".txt", ".json", ".yaml", ".yml",
    ".env", ".cfg", ".ini", ".toml",
}
MAX_PROJECT_SIZE_MB: int = 50
MAX_SINGLE_FILE_MB: int = 5

DANGER_PATTERNS = [
    "os.system",
    "__import__('os')",
    "__import__(\"os\")",
    "eval(",
    "exec(",
    "compile(",
    "rm -rf",
    "chmod 777",
    ":(){:|:&};:",        # classic fork bomb
    "subprocess.Popen",   # heavy red flag, will only warn
    "socket.socket(socket.AF_INET, socket.SOCK_RAW",
]

# Run-command shell-meta blacklist (rejected outright)
RUN_CMD_BLOCK_CHARS = [";", "|", "&&", "||", "`", "$(", ">", "<", "\\"]

# Smart hints
ERROR_HINTS: Dict[str, str] = {
    "KeyError":                "ENV variable missing. Go to 🔐 ENV Setup.",
    "ModuleNotFoundError":     "Package not installed. Use 📦 Install Deps.",
    "ImportError":             "Import failed. Check your dependencies (📦 Install Deps).",
    "ConnectionRefusedError":  "Can't connect to external service. Check your API URL.",
    "PermissionError":         "File permission issue inside container.",
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

# ────────────────────────────────────────────────────────────
# Docker container template
# ────────────────────────────────────────────────────────────
PYTHON_IMAGES = {
    "3.10": "python:3.10-slim",
    "3.11": "python:3.11-slim",
    "3.12": "python:3.12-slim",
}
DEFAULT_PYTHON_VERSION = "3.12"

CONTAINER_LABEL_PREFIX = "pyhost"     # docker labels: pyhost.project_id=<uuid>

# Rate limit
RATE_LIMIT_REQUESTS_PER_MIN: int = 30
RATE_LIMIT_WINDOW_SEC: int = 60

# Web app (Premium)
PUBLIC_DOMAIN: str = os.getenv("PUBLIC_DOMAIN", "https://pyhost.example.com").rstrip("/")
NGINX_SITES_DIR: str = os.getenv("NGINX_SITES_DIR", "/etc/nginx/sites-enabled")

# User-data directory layout
USER_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "user_data"))
TEMP_DIR    = os.path.join(USER_DATA_DIR, "temp")
BACKUP_DIR  = os.path.join(USER_DATA_DIR, "backups")
ERRLOG_DIR  = os.path.join(USER_DATA_DIR, "error_logs")
PROJECTS_DIR = os.path.join(USER_DATA_DIR, "projects")

for _d in (TEMP_DIR, BACKUP_DIR, ERRLOG_DIR, PROJECTS_DIR):
    os.makedirs(_d, exist_ok=True)

# Welcome banner
WELCOME_BANNER_PATH = os.path.join(os.path.dirname(__file__), "assets", "welcome_banner.jpg")

# Custom emoji ids (require Premium for the *bot*; helper uses them only when premium is on)
CUSTOM_EMOJI_FIRE  = "5368324170671202286"
CUSTOM_EMOJI_STAR  = "5310169226856644648"
CUSTOM_EMOJI_HEART = "5285430309720966085"
BOT_HAS_PREMIUM = os.getenv("BOT_HAS_PREMIUM", "false").lower() == "true"
