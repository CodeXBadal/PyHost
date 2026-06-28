"""
Nginx site config generator (Premium feature).

Renders templates/nginx_site.conf.j2 into NGINX_SITES_DIR/<project_name>.conf
and (when configured) calls `nginx -s reload`.

Best-effort: in environments without nginx the function still returns the
public URL so the bot UI keeps working.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Tuple

from jinja2 import Environment, FileSystemLoader

from config import NGINX_SITES_DIR, PUBLIC_DOMAIN

log = logging.getLogger(__name__)

_TPL_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
_env = Environment(loader=FileSystemLoader(_TPL_DIR), keep_trailing_newline=True)


def _sanitize_project_name(project_name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9-]+", "-", (project_name or "").strip())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned or "app"


def public_url(project_name: str) -> str:
    domain = PUBLIC_DOMAIN.rstrip("/")
    safe_name = _sanitize_project_name(project_name)
    return f"{domain}/app/{safe_name}"


async def configure_proxy(project_name: str, project_id: str, port: int) -> Tuple[bool, str]:
    """Generate /etc/nginx/sites-enabled/<project>.conf and reload."""
    try:
        tpl = _env.get_template("nginx_site.conf.j2")
    except Exception as exc:
        return False, f"missing template: {exc}"

    safe_project_name = _sanitize_project_name(project_name)
    container_name = f"pyhost_{project_id}"
    content = tpl.render(
        project_name=safe_project_name,
        container_name=container_name,
        port=port,
        public_domain=PUBLIC_DOMAIN,
    )

    try:
        os.makedirs(NGINX_SITES_DIR, exist_ok=True)
        target = os.path.join(NGINX_SITES_DIR, f"{safe_project_name}.conf")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(content)
    except PermissionError:
        return False, f"cannot write to {NGINX_SITES_DIR} (permission denied)"
    except Exception as exc:
        return False, f"write failed: {exc}"

    # best-effort reload
    # SECURITY: use exec form (no shell) instead of create_subprocess_shell,
    # which is equivalent to shell=True.
    try:
        proc = await asyncio.create_subprocess_exec(
            "nginx", "-s", "reload",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
    except Exception as exc:
        log.debug("nginx reload skipped: %s", exc)
    return True, public_url(safe_project_name)
