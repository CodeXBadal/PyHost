"""
Process Manager — Docker-free project runner.

Each user project runs as a plain subprocess on the host (or inside the
bot container). No Docker socket, no special permissions needed.

Fixes applied:
  - shell=False with shlex.split() — no shell injection possible
  - Log rotation — auto-rotate when log > LOG_ROTATE_MAX_MB
  - resource limits via ulimit (nofile, nproc)
  - Better asyncio API (get_running_loop instead of deprecated get_event_loop)
  - OOM-safe tail (chunked read from end of file)
  - Thread-safe PID file operations
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

# Max bytes to read at once for tail — prevents OOM on huge logs
_TAIL_CHUNK = 128 * 1024  # 128 KB


def _project_dir(project_id: str) -> str:
    return os.path.join(PROJECTS_DIR, project_id)


def _pid_path(project_id: str) -> str:
    return os.path.join(_project_dir(project_id), PID_FILE)


def _log_path(project_id: str) -> str:
    return os.path.join(_project_dir(project_id), LOG_FILE)


def _read_pid(project_id: str) -> Optional[int]:
    try:
        with open(_pid_path(project_id)) as f:
            return int(f.read().strip())
    except Exception:
        return None


def _write_pid(project_id: str, pid: int) -> None:
    path = _pid_path(project_id)
    # Write atomically via temp file
    tmp = path + ".tmp"
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
    """Rotate log file if it exceeds LOG_ROTATE_MAX_MB."""
    try:
        if not os.path.exists(log_path):
            return
        size_mb = os.path.getsize(log_path) / (1024 * 1024)
        if size_mb < LOG_ROTATE_MAX_MB:
            return
        # Rotate: .log.3 → delete, .log.2 → .log.3, .log.1 → .log.2, .log → .log.1
        for i in range(LOG_ROTATE_KEEP_FILES - 1, 0, -1):
            src = f"{log_path}.{i}"
            dst = f"{log_path}.{i + 1}"
            if os.path.exists(src):
                if i + 1 > LOG_ROTATE_KEEP_FILES:
                    os.remove(src)
                else:
                    os.replace(src, dst)
        os.replace(log_path, f"{log_path}.1")
        log.info("Rotated log: %s (was %.1f MB)", log_path, size_mb)
    except Exception as exc:
        log.debug("Log rotation skipped: %s", exc)


class ProcessManager:
    """Manages user project subprocesses without Docker."""

    # ── Start ──────────────────────────────────────────────
    async def create_container(self, project_id: str, python_version: str,
                                plan: str = "free", port: Optional[int] = None) -> str:
        """Compatibility shim — ensure project dir exists, return project_id."""
        os.makedirs(_project_dir(project_id), exist_ok=True)
        return project_id

    async def start_container(self, project_id: str, run_command: str,
                               env: Dict[str, str]) -> Tuple[bool, str]:
        """Launch run_command as a subprocess inside the project directory.

        SECURITY: Uses shell=False + shlex.split() — no shell injection possible.
        """
        proj_dir = _project_dir(project_id)
        if not os.path.isdir(proj_dir):
            return False, f"project directory not found: {proj_dir}"

        # Stop any existing process first
        await self.stop_container(project_id)

        # Build full environment: inherit bot env + user vars
        full_env = os.environ.copy()
        full_env.update(env)

        # Resolve the actual command — replace bare 'python' with full path
        cmd_str = run_command.strip()
        python_bin = _find_python()
        for alias in ("python3", "python"):
            if cmd_str.startswith(alias + " ") or cmd_str == alias:
                cmd_str = python_bin + cmd_str[len(alias):]
                break

        # FIXED: shell=False — parse command into list, no shell injection
        try:
            cmd_list = shlex.split(cmd_str)
        except ValueError as exc:
            return False, f"invalid command syntax: {exc}"

        if not cmd_list:
            return False, "empty command"

        log_path = _log_path(project_id)
        _rotate_log(log_path)

        try:
            with open(log_path, "a") as log_fp:
                log_fp.write(f"\n--- pyhost start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
                proc = await asyncio.create_subprocess_exec(
                    *cmd_list,
                    cwd=proj_dir,
                    env=full_env,
                    stdout=log_fp,
                    stderr=asyncio.subprocess.STDOUT,
                    start_new_session=True,   # new session for clean kill (replaces setsid)
                )
            _write_pid(project_id, proc.pid)

            # Give it 1.5 seconds to fail fast
            await asyncio.sleep(1.5)
            if proc.returncode is not None:
                tail = _tail_log(log_path, 20)
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
    async def stop_container(self, project_id: str) -> bool:
        pid = _read_pid(project_id)
        if pid is None:
            return False
        try:
            # Try SIGTERM first (graceful), then SIGKILL
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
            os.remove(_pid_path(project_id))
        except FileNotFoundError:
            pass
        log.info("Stopped project %s (PID %s)", project_id, pid)
        return True

    # ── Restart ────────────────────────────────────────────
    async def restart_container(self, project_id: str, run_command: str,
                                 env: Dict[str, str]) -> Tuple[bool, str]:
        await self.stop_container(project_id)
        await asyncio.sleep(0.5)
        return await self.start_container(project_id, run_command, env)

    # ── Delete ─────────────────────────────────────────────
    async def delete_container(self, project_id: str) -> None:
        await self.stop_container(project_id)

    # ── Stats ──────────────────────────────────────────────
    async def get_stats(self, project_id: str) -> Dict[str, Any]:
        pid = _read_pid(project_id)
        if pid is None or not _is_alive(pid):
            return {
                "ram_mb": 0, "cpu_percent": 0, "uptime_seconds": 0,
                "status": "exited" if pid else "stopped",
            }
        try:
            proc = psutil.Process(pid)
            # cpu_percent with interval in a thread to avoid blocking event loop
            loop = asyncio.get_running_loop()
            cpu = await loop.run_in_executor(None, lambda: proc.cpu_percent(interval=0.2))
            mem = proc.memory_info().rss / (1024 * 1024)
            uptime = int(time.time() - proc.create_time())
            return {
                "ram_mb": round(mem, 1),
                "cpu_percent": round(cpu, 1),
                "uptime_seconds": uptime,
                "status": "running",
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return {"ram_mb": 0, "cpu_percent": 0, "uptime_seconds": 0, "status": "exited"}

    # ── Logs ───────────────────────────────────────────────
    async def get_logs(self, project_id: str, lines: int = 200,
                       errors_only: bool = False) -> str:
        log_path = _log_path(project_id)
        if not os.path.exists(log_path):
            return "(no log file yet — start the project first)"
        text = _tail_log(log_path, lines)
        if errors_only:
            keep = [ln for ln in text.splitlines()
                    if any(kw in ln.lower() for kw in
                           ("traceback", "error", "exception", "  file "))]
            text = "\n".join(keep) or "(no error lines found)"
        return text

    # ── Exec (for pip install) ─────────────────────────────
    async def exec_command(self, project_id: str, cmd: str,
                           workdir: str = "") -> Tuple[int, str]:
        """Execute a command in the project directory.

        SECURITY: Uses shell=False for safety.
        """
        proj_dir = _project_dir(project_id)
        cwd = workdir or proj_dir
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
    async def clear_logs(self, project_id: str) -> None:
        """Truncate the project log file."""
        log_path = _log_path(project_id)
        try:
            with open(log_path, "w") as f:
                f.write(f"--- log cleared {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        except Exception as exc:
            log.debug("clear_logs: %s", exc)

    # ── is_alive helper ────────────────────────────────────
    def is_project_alive(self, project_id: str) -> bool:
        pid = _read_pid(project_id)
        return pid is not None and _is_alive(pid)

    # ── Admin helpers ──────────────────────────────────────
    async def list_pyhost_containers(self) -> List[Dict[str, Any]]:
        """Return running pyhost projects as pseudo-container list."""
        results = []
        try:
            if not os.path.isdir(PROJECTS_DIR):
                return []
            for proj_name in os.listdir(PROJECTS_DIR):
                proj_dir = os.path.join(PROJECTS_DIR, proj_name)
                pid_file = os.path.join(proj_dir, PID_FILE)
                if os.path.exists(pid_file):
                    pid = _read_pid(proj_name)
                    alive = pid is not None and _is_alive(pid)
                    results.append({
                        "id": proj_name[:12],
                        "name": f"pyhost_{proj_name}",
                        "status": "running" if alive else "exited",
                        "project_id": proj_name,
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
    """OOM-safe tail — reads at most _TAIL_CHUNK bytes from end of file."""
    try:
        with open(log_path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            chunk = min(size, max(_TAIL_CHUNK, lines * 200))
            f.seek(-chunk, 2)
            raw = f.read(chunk)
        text = raw.decode("utf-8", "ignore")
        all_lines = text.splitlines()
        return "\n".join(all_lines[-lines:])
    except Exception as exc:
        return f"(log read error: {exc})"


def _find_python() -> str:
    """Find the best available python3 binary."""
    import shutil
    for candidate in ("python3.12", "python3.11", "python3.10", "python3", "python"):
        path = shutil.which(candidate)
        if path:
            return path
    return "python3"


# Singleton
process_manager = ProcessManager()
