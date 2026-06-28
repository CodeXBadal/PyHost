"""
Process Manager — Docker-free project runner.

Each user project runs as a plain subprocess on the host (or inside the
bot container). No Docker socket, no special permissions needed.

Directory layout:  projects/<user_id>/<project_name>/

Python version isolation:
  • If the project's .venv was created with the correct python version,
    `start_container` uses `.venv/bin/python` directly.
  • The venv is created by `dependency_installer.ensure_venv()` which
    receives the requested python_version string (e.g. "3.11").
"""
from __future__ import annotations

import asyncio
import logging
import os
import shlex
import signal
import time
from typing import Any, Dict, List, Optional, Tuple

import psutil

from config import PROJECTS_DIR, PLAN_LIMITS, LOG_ROTATE_MAX_MB, LOG_ROTATE_KEEP_FILES

log = logging.getLogger(__name__)

PID_FILE = ".pyhost.pid"
LOG_FILE = ".pyhost.log"

_TAIL_CHUNK = 128 * 1024  # 128 KB

# ── Environment isolation ───────────────────────────────────
_SAFE_SYSTEM_VARS = {
    "PATH", "HOME", "USER", "LANG", "LC_ALL", "LC_CTYPE",
    "TZ", "TERM", "TMPDIR", "PYTHONPATH", "PYTHONDONTWRITEBYTECODE",
}
_BOT_SECRET_VARS = {
    "BOT_TOKEN", "MONGO_URI", "MONGO_DB_NAME", "ENCRYPTION_KEY",
    "ADMIN_IDS", "REDIS_URL", "FORCE_JOIN_CHANNEL",
    "PUBLIC_DOMAIN", "NGINX_SITES_DIR",
}


def _project_dir(project_id: str,
                 user_id: int | str | None = None,
                 name: str | None = None) -> str:
    """Resolve on-disk project directory.

    Prefers user_id + name (new-style) when provided.
    Falls back to bare project_id for tmp/pending dirs.
    """
    from core.file_handler import project_path
    return project_path(project_id, user_id, name)


def _pid_path(proj_dir: str) -> str:
    return os.path.join(proj_dir, PID_FILE)


def _log_path(proj_dir: str) -> str:
    return os.path.join(proj_dir, LOG_FILE)


def _read_pid(proj_dir: str) -> Optional[int]:
    try:
        with open(_pid_path(proj_dir)) as f:
            return int(f.read().strip())
    except Exception:
        return None


def _write_pid(proj_dir: str, pid: int) -> None:
    path = _pid_path(proj_dir)
    tmp  = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(str(pid))
    os.replace(tmp, path)


def _is_alive(pid: int) -> bool:
    try:
        proc = psutil.Process(pid)
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def _rotate_log(log_path: str) -> None:
    try:
        if not os.path.exists(log_path):
            return
        size_mb = os.path.getsize(log_path) / (1024 * 1024)
        if size_mb < LOG_ROTATE_MAX_MB:
            return
        for i in range(LOG_ROTATE_KEEP_FILES - 1, 0, -1):
            src = f"{log_path}.{i}"
            dst = f"{log_path}.{i + 1}"
            if os.path.exists(src):
                if i + 1 > LOG_ROTATE_KEEP_FILES:
                    os.remove(src)
                else:
                    os.replace(src, dst)
        os.replace(log_path, f"{log_path}.1")
    except Exception as exc:
        log.debug("Log rotation skipped: %s", exc)


class ProcessManager:
    """Manages user project subprocesses without Docker."""

    # ── Start ──────────────────────────────────────────────
    async def create_container(self, project_id: str, python_version: str,
                                plan: str = "free", port: Optional[int] = None,
                                user_id: int | str | None = None,
                                name: str | None = None) -> str:
        """Ensure project dir exists, return project_id."""
        os.makedirs(_project_dir(project_id, user_id, name), exist_ok=True)
        return project_id

    async def start_container(self, project_id: str, run_command: str,
                               env: Dict[str, str],
                               user_id: int | str | None = None,
                               proj_name: str | None = None) -> Tuple[bool, str]:
        """Launch run_command as a subprocess inside the project directory."""
        proj_dir = _project_dir(project_id, user_id, proj_name)
        if not os.path.isdir(proj_dir):
            return False, f"project directory not found: {proj_dir}"

        await self.stop_container(project_id, user_id=user_id, proj_name=proj_name)

        # Build clean child environment
        full_env: Dict[str, str] = {}
        for key in _SAFE_SYSTEM_VARS:
            if key in os.environ and key not in _BOT_SECRET_VARS:
                full_env[key] = os.environ[key]
        for key, value in env.items():
            if key in _BOT_SECRET_VARS:
                log.warning("Refusing bot-secret env var %s for project %s", key, project_id)
                continue
            full_env[key] = value

        # ── Python version resolution ───────────────────────
        # Priority:  .venv/bin/python  >  system pythonX.Y  >  any python3
        cmd_str     = run_command.strip()
        venv_python = os.path.join(proj_dir, ".venv", "bin", "python")

        if os.path.isfile(venv_python):
            python_bin = venv_python
            log.info("Using venv python for project %s: %s", project_id, venv_python)
        else:
            python_bin = _find_python()
            log.warning("No venv found for project %s — falling back to %s",
                        project_id, python_bin)

        # Replace any python alias in run_command with the resolved binary
        replaced = False
        for alias in ("python3.12", "python3.11", "python3.10", "python3.9",
                      "python3.8", "python3", "python"):
            if cmd_str == alias:
                cmd_str  = python_bin
                replaced = True
                break
            if cmd_str.startswith(alias + " "):
                cmd_str  = python_bin + cmd_str[len(alias):]
                replaced = True
                break
        if not replaced:
            log.debug("run_command %r has no python alias — used as-is", cmd_str)

        try:
            cmd_list = shlex.split(cmd_str)
        except ValueError as exc:
            return False, f"invalid command syntax: {exc}"
        if not cmd_list:
            return False, "empty command"

        lpath = _log_path(proj_dir)
        _rotate_log(lpath)

        # BUG-048: start_new_session=True is ignored on Windows but harmless.
        # We pass it unconditionally because PyHost is documented as
        # Linux-only (see Dockerfile / docker-compose.yml).  Process-group
        # control is required for clean SIGTERM/SIGKILL of children.
        #
        # BUG-040 (defence-in-depth): full_env is an isolated dict that
        # does NOT inherit os.environ unless we explicitly copied a key
        # via _SAFE_SYSTEM_VARS.  This blocks direct reads of BOT_TOKEN
        # etc.  A malicious child could still walk /proc/<parent>/environ
        # on a non-namespaced host — deployment guidance: run the bot
        # inside a container or with hidepid=2 mounted /proc.
        subprocess_kwargs = dict(
            cwd=proj_dir,
            env=full_env,
            stderr=asyncio.subprocess.STDOUT,
        )
        if os.name == "posix":
            subprocess_kwargs["start_new_session"] = True

        try:
            with open(lpath, "a") as log_fp:
                log_fp.write(f"\n--- pyhost start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
                proc = await asyncio.create_subprocess_exec(
                    *cmd_list,
                    stdout=log_fp,
                    **subprocess_kwargs,
                )
            _write_pid(proj_dir, proc.pid)

            await asyncio.sleep(1.5)
            if proc.returncode is not None:
                tail = _tail_log(lpath, 20)
                return False, f"process exited immediately:\n{tail}"

            log.info("Started project %s PID=%d cmd=%r", project_id, proc.pid, cmd_str)
            return True, ""
        except FileNotFoundError:
            return False, f"executable not found: {cmd_list[0]}"
        except PermissionError:
            return False, f"permission denied: {cmd_list[0]}"
        except Exception as exc:
            return False, str(exc)

    # ── Stop ───────────────────────────────────────────────
    async def stop_container(self, project_id: str,
                              user_id: int | str | None = None,
                              proj_name: str | None = None) -> bool:
        proj_dir = _project_dir(project_id, user_id, proj_name)
        pid = _read_pid(proj_dir)
        if pid is None:
            return False
        try:
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
            await asyncio.sleep(0.8)
            if _is_alive(pid):
                try:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
        except Exception as exc:
            log.debug("stop_container: %s", exc)
        try:
            os.remove(_pid_path(proj_dir))
        except FileNotFoundError:
            pass
        log.info("Stopped project %s (PID %s)", project_id, pid)
        return True

    # ── Restart ────────────────────────────────────────────
    async def restart_container(self, project_id: str, run_command: str,
                                 env: Dict[str, str],
                                 user_id: int | str | None = None,
                                 proj_name: str | None = None) -> Tuple[bool, str]:
        await self.stop_container(project_id, user_id=user_id, proj_name=proj_name)
        await asyncio.sleep(0.5)
        return await self.start_container(project_id, run_command, env,
                                          user_id=user_id, proj_name=proj_name)

    # ── Delete ─────────────────────────────────────────────
    async def delete_container(self, project_id: str,
                                user_id: int | str | None = None,
                                proj_name: str | None = None) -> None:
        await self.stop_container(project_id, user_id=user_id, proj_name=proj_name)

    # ── Stats ──────────────────────────────────────────────
    async def get_stats(self, project_id: str,
                        user_id: int | str | None = None,
                        proj_name: str | None = None) -> Dict[str, Any]:
        proj_dir = _project_dir(project_id, user_id, proj_name)
        pid = _read_pid(proj_dir)
        if pid is None or not _is_alive(pid):
            return {
                "ram_mb": 0, "cpu_percent": 0, "uptime_seconds": 0,
                "status": "exited" if pid else "stopped",
            }
        try:
            proc  = psutil.Process(pid)
            loop  = asyncio.get_running_loop()
            cpu   = await loop.run_in_executor(None, lambda: proc.cpu_percent(interval=0.2))
            mem   = proc.memory_info().rss / (1024 * 1024)
            uptime = int(time.time() - proc.create_time())
            return {
                "ram_mb":        round(mem, 1),
                "cpu_percent":   round(cpu, 1),
                "uptime_seconds": uptime,
                "status":        "running",
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return {"ram_mb": 0, "cpu_percent": 0, "uptime_seconds": 0, "status": "exited"}

    # ── Logs ───────────────────────────────────────────────
    async def get_logs(self, project_id: str, lines: int = 200,
                       errors_only: bool = False,
                       user_id: int | str | None = None,
                       proj_name: str | None = None) -> str:
        proj_dir = _project_dir(project_id, user_id, proj_name)
        lpath    = _log_path(proj_dir)
        if not os.path.exists(lpath):
            return "(no log file yet — start the project first)"
        text = _tail_log(lpath, lines)
        if errors_only:
            keep = [ln for ln in text.splitlines()
                    if any(kw in ln.lower() for kw in
                           ("traceback", "error", "exception", "  file "))]
            text = "\n".join(keep) or "(no error lines found)"
        return text

    # ── Exec (for pip install / venv creation) ─────────────
    async def exec_command(self, project_id: str, cmd: str,
                           workdir: str = "",
                           user_id: int | str | None = None,
                           proj_name: str | None = None) -> Tuple[int, str]:
        proj_dir = _project_dir(project_id, user_id, proj_name)
        cwd      = workdir or proj_dir
        try:
            cmd_list = shlex.split(cmd)
        except ValueError as exc:
            return 1, f"invalid command: {exc}"
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_list,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
                return 1, "command timed out (300s)"
            output = stdout.decode("utf-8", "ignore") if stdout else ""
            return proc.returncode or 0, output
        except FileNotFoundError:
            return 1, f"command not found: {cmd_list[0] if cmd_list else cmd}"
        except Exception as exc:
            return 1, str(exc)

    # ── Clear log ──────────────────────────────────────────
    async def clear_logs(self, project_id: str,
                         user_id: int | str | None = None,
                         proj_name: str | None = None) -> None:
        proj_dir = _project_dir(project_id, user_id, proj_name)
        lpath    = _log_path(proj_dir)
        try:
            with open(lpath, "w") as f:
                f.write(f"--- log cleared {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        except Exception as exc:
            log.debug("clear_logs: %s", exc)

    def is_project_alive(self, project_id: str,
                         user_id: int | str | None = None,
                         proj_name: str | None = None) -> bool:
        proj_dir = _project_dir(project_id, user_id, proj_name)
        pid = _read_pid(proj_dir)
        return pid is not None and _is_alive(pid)

    async def list_pyhost_containers(self) -> List[Dict[str, Any]]:
        """Return running pyhost projects as pseudo-container list."""
        results = []
        try:
            if not os.path.isdir(PROJECTS_DIR):
                return []
            # New layout: projects/<user_id>/<project_name>/
            for uid_dir in os.listdir(PROJECTS_DIR):
                uid_path = os.path.join(PROJECTS_DIR, uid_dir)
                if not os.path.isdir(uid_path):
                    continue
                for proj_name in os.listdir(uid_path):
                    proj_dir = os.path.join(uid_path, proj_name)
                    pid_file = os.path.join(proj_dir, PID_FILE)
                    if os.path.exists(pid_file):
                        pid   = _read_pid(proj_dir)
                        alive = pid is not None and _is_alive(pid)
                        results.append({
                            "id":         f"{uid_dir}/{proj_name}",
                            "name":       f"pyhost_{uid_dir}_{proj_name}",
                            "status":     "running" if alive else "exited",
                            "project_id": f"{uid_dir}/{proj_name}",
                        })
        except Exception as exc:
            log.debug("list_pyhost_containers error: %s", exc)
        return results

    async def cleanup_dead(self, valid_project_ids: set) -> int:
        n = 0
        for info in await self.list_pyhost_containers():
            if info["project_id"] not in valid_project_ids:
                await self.stop_container(info["project_id"])
                n += 1
        return n

    def ping(self) -> bool:
        return True

    def _ensure_client(self) -> bool:
        return True


# ── Helpers ────────────────────────────────────────────────
def _tail_log(log_path: str, lines: int) -> str:
    try:
        with open(log_path, "rb") as f:
            f.seek(0, 2)
            size  = f.tell()
            chunk = min(size, max(_TAIL_CHUNK, lines * 200))
            f.seek(-chunk, 2)
            raw   = f.read(chunk)
        text      = raw.decode("utf-8", "ignore")
        all_lines = text.splitlines()
        return "\n".join(all_lines[-lines:])
    except Exception as exc:
        return f"(log read error: {exc})"


def _find_python(version: str | None = None) -> str:
    """Find the best available python binary for the given version string.

    version examples: "3.11", "3.12", "3.10"
    Falls back through available versions if the exact one isn't found.

    FIX for BUG-052: 3.13 and 3.14 are now in the fallback list so newer
    hosts can resolve them.  The order is newest-first within the modern
    range, oldest-last so EOL versions are picked only as last resort.
    """
    import shutil

    candidates: list[str] = []
    if version:
        candidates.append(f"python{version}")        # python3.11
        major = version.split(".")[0]
        candidates.append(f"python{major}")           # python3
    candidates += [
        "python3.14", "python3.13",
        "python3.12", "python3.11", "python3.10",
        "python3.9", "python3.8", "python3", "python",
    ]

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        path = shutil.which(candidate)
        if path:
            return path
    return "python3"


# Singleton
process_manager = ProcessManager()
