"""
Docker container lifecycle for user projects.

Each project lives in its own container based on `python:3.X-slim`,
bind-mounted from PROJECTS_DIR/<project_id>. The bot runs the project's
configured run command inside the container via `docker exec`-equivalent.

Implementation notes:
  • We use the synchronous `docker` SDK from inside `asyncio.to_thread`
    so we never block the event loop.
  • Containers are tagged with labels:  pyhost.project_id=<id>
"""
from __future__ import annotations

import asyncio
import logging
import os
import shlex
from typing import Any, Dict, List, Optional, Tuple

import docker
from docker.errors import APIError, NotFound

from config import (
    CONTAINER_LABEL_PREFIX, PLAN_LIMITS, PYTHON_IMAGES,
    PROJECTS_DIR,
)

log = logging.getLogger(__name__)


class DockerManager:
    def __init__(self) -> None:
        try:
            self.client = docker.from_env()
        except Exception as exc:  # pragma: no cover
            log.exception("Cannot connect to Docker daemon: %s", exc)
            self.client = None

    # ── helpers ────────────────────────────────────────────
    def _to_thread(self, fn, *args, **kwargs):
        return asyncio.get_event_loop().run_in_executor(None, lambda: fn(*args, **kwargs))

    def _container_name(self, project_id: str) -> str:
        return f"pyhost_{project_id}"

    def _project_path(self, project_id: str) -> str:
        return os.path.join(PROJECTS_DIR, project_id)

    def _resource_limits(self, plan: str) -> Dict[str, Any]:
        limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
        return {
            "mem_limit":  f"{int(limits['ram_mb'])}m",
            "memswap_limit": f"{int(limits['ram_mb'])}m",  # no swap
            "nano_cpus":  int(limits["cpu"] * 1e9),
            "pids_limit": 50,
        }

    # ── lifecycle ──────────────────────────────────────────
    async def create_container(self, project_id: str, python_version: str,
                               plan: str = "free", port: Optional[int] = None) -> str:
        if self.client is None:
            raise RuntimeError("Docker daemon unavailable")

        image = PYTHON_IMAGES.get(python_version, PYTHON_IMAGES["3.12"])
        name = self._container_name(project_id)
        host_path = self._project_path(project_id)
        os.makedirs(host_path, exist_ok=True)

        # remove dead leftover container with same name if any
        await self._safe_remove(name)

        # pull image (async-safe via to_thread)
        await self._to_thread(self.client.images.pull, image)

        limits = self._resource_limits(plan)
        labels = {
            f"{CONTAINER_LABEL_PREFIX}.project_id": project_id,
        }

        ports_arg = {f"{port}/tcp": None} if port else None  # publish random host port

        def _run():
            return self.client.containers.create(
                image=image,
                name=name,
                command=["sleep", "infinity"],         # keep alive; exec real cmd later
                working_dir="/app",
                volumes={host_path: {"bind": "/app", "mode": "rw"}},
                tmpfs={"/tmp": "size=50m"},
                network_mode="bridge",
                security_opt=["no-new-privileges:true"],
                cap_drop=["ALL"],
                labels=labels,
                detach=True,
                ports=ports_arg,
                **limits,
            )

        cont = await self._to_thread(_run)
        log.info("Created container %s for project %s", cont.id[:12], project_id)
        return cont.id

    async def _safe_remove(self, name: str) -> None:
        if self.client is None:
            return
        try:
            cont = await self._to_thread(self.client.containers.get, name)
            await self._to_thread(cont.remove, force=True)
        except NotFound:
            return
        except Exception as exc:
            log.debug("safe_remove(%s): %s", name, exc)

    async def start_container(self, project_id: str, run_command: str,
                              env: Dict[str, str]) -> Tuple[bool, str]:
        """Start the container (if stopped) and exec the run command in background."""
        if self.client is None:
            return False, "Docker daemon unavailable"
        name = self._container_name(project_id)
        try:
            cont = await self._to_thread(self.client.containers.get, name)
        except NotFound:
            return False, "container does not exist"

        try:
            await self._to_thread(cont.start)
        except APIError as exc:
            if "is already started" not in str(exc):
                return False, f"docker start failed: {exc.explanation}"

        # write a small env file inside the container then exec the run command
        env_lines = "\n".join(f"export {k}={shlex.quote(v)}" for k, v in env.items())
        bootstrap = (
            f"cat > /tmp/_pyhost_env.sh <<'__EOF__'\n{env_lines}\n__EOF__\n"
            f"chmod +x /tmp/_pyhost_env.sh\n"
            f"echo '--- pyhost start ---' >> /tmp/pyhost.log\n"
            f"(source /tmp/_pyhost_env.sh && cd /app && exec {run_command}) "
            f">> /tmp/pyhost.log 2>&1 &\n"
            f"echo $! > /tmp/pyhost.pid\n"
        )

        def _exec():
            return cont.exec_run(["/bin/sh", "-lc", bootstrap], detach=False)

        try:
            result = await self._to_thread(_exec)
            output = (result.output or b"").decode("utf-8", "ignore")
            if result.exit_code not in (0, None):
                return False, f"start exec failed: {output.strip()}"
        except Exception as exc:
            return False, f"exec error: {exc}"

        return True, ""

    async def stop_container(self, project_id: str) -> bool:
        if self.client is None:
            return False
        name = self._container_name(project_id)
        try:
            cont = await self._to_thread(self.client.containers.get, name)
            await self._to_thread(cont.stop, timeout=10)
            return True
        except NotFound:
            return False
        except Exception as exc:
            log.warning("stop_container(%s): %s", project_id, exc)
            return False

    async def restart_container(self, project_id: str, run_command: str,
                                env: Dict[str, str]) -> Tuple[bool, str]:
        await self.stop_container(project_id)
        return await self.start_container(project_id, run_command, env)

    async def delete_container(self, project_id: str) -> None:
        await self._safe_remove(self._container_name(project_id))

    # ── stats / logs ───────────────────────────────────────
    async def get_stats(self, project_id: str) -> Dict[str, float]:
        if self.client is None:
            return {"ram_mb": 0, "cpu_percent": 0, "uptime_seconds": 0, "status": "unavailable"}
        name = self._container_name(project_id)
        try:
            cont = await self._to_thread(self.client.containers.get, name)
            stats = await self._to_thread(cont.stats, stream=False)
        except NotFound:
            return {"ram_mb": 0, "cpu_percent": 0, "uptime_seconds": 0, "status": "missing"}
        except Exception as exc:
            log.debug("stats error %s: %s", project_id, exc)
            return {"ram_mb": 0, "cpu_percent": 0, "uptime_seconds": 0, "status": "error"}

        try:
            mem_usage = stats["memory_stats"].get("usage", 0)
            ram_mb = mem_usage / (1024 * 1024)
        except Exception:
            ram_mb = 0.0

        try:
            cpu_delta = (stats["cpu_stats"]["cpu_usage"]["total_usage"]
                         - stats["precpu_stats"]["cpu_usage"]["total_usage"])
            sys_delta = (stats["cpu_stats"]["system_cpu_usage"]
                         - stats["precpu_stats"]["system_cpu_usage"])
            ncpu = stats["cpu_stats"].get("online_cpus") or 1
            cpu_pct = (cpu_delta / sys_delta) * ncpu * 100 if sys_delta > 0 else 0.0
        except Exception:
            cpu_pct = 0.0

        # uptime
        try:
            from datetime import datetime, timezone
            started = cont.attrs["State"]["StartedAt"]
            # docker returns ISO 8601; strip trailing 'Z' / nanoseconds
            from dateutil import parser
            t = parser.isoparse(started)
            uptime = (datetime.now(timezone.utc) - t).total_seconds()
        except Exception:
            uptime = 0

        status = (cont.attrs.get("State", {}).get("Status") or "unknown")
        return {
            "ram_mb": round(ram_mb, 1),
            "cpu_percent": round(cpu_pct, 1),
            "uptime_seconds": int(uptime),
            "status": status,
        }

    async def get_logs(self, project_id: str, lines: int = 200,
                       errors_only: bool = False) -> str:
        if self.client is None:
            return "(Docker daemon unavailable)"
        name = self._container_name(project_id)
        try:
            cont = await self._to_thread(self.client.containers.get, name)
        except NotFound:
            return "(no container)"
        try:
            tail = "all" if lines >= 99999 else str(lines)
            res = await self._to_thread(
                cont.exec_run,
                ["/bin/sh", "-lc", f"tail -n {tail} /tmp/pyhost.log 2>/dev/null || echo '(no log)'"],
            )
            text = (res.output or b"").decode("utf-8", "ignore")
        except Exception as exc:
            return f"(log error: {exc})"

        if errors_only:
            keep = []
            for line in text.splitlines():
                low = line.lower()
                if ("traceback" in low or "error" in low or "exception" in low
                        or line.startswith("  File ")):
                    keep.append(line)
            text = "\n".join(keep) or "(no error lines found)"
        return text

    async def exec_command(self, project_id: str, cmd: str,
                           workdir: str = "/app") -> Tuple[int, str]:
        if self.client is None:
            return 1, "Docker daemon unavailable"
        name = self._container_name(project_id)
        try:
            cont = await self._to_thread(self.client.containers.get, name)
        except NotFound:
            return 127, "container not found"
        try:
            res = await self._to_thread(
                cont.exec_run, ["/bin/sh", "-lc", cmd], workdir=workdir,
            )
            return res.exit_code or 0, (res.output or b"").decode("utf-8", "ignore")
        except Exception as exc:
            return 1, str(exc)

    # ── admin helpers ──────────────────────────────────────
    async def list_pyhost_containers(self) -> List[Dict[str, Any]]:
        if self.client is None:
            return []
        try:
            conts = await self._to_thread(
                self.client.containers.list,
                all=True,
                filters={"label": f"{CONTAINER_LABEL_PREFIX}.project_id"},
            )
        except Exception:
            return []
        out = []
        for c in conts:
            out.append({
                "id":         c.id[:12],
                "name":       c.name,
                "status":     c.status,
                "project_id": c.labels.get(f"{CONTAINER_LABEL_PREFIX}.project_id"),
            })
        return out

    async def cleanup_dead(self, valid_project_ids: set) -> int:
        """Remove pyhost-labelled containers whose project no longer exists."""
        n = 0
        for info in await self.list_pyhost_containers():
            if info["project_id"] not in valid_project_ids:
                await self._safe_remove(info["name"])
                n += 1
        return n


docker_manager = DockerManager()
