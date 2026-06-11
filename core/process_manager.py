"""
Process Manager — Docker-free project runner.

Replaces docker_manager entirely. Each user project runs as a plain
subprocess on the host (or inside the bot container). No Docker socket,
no special permissions needed.

Process lifecycle:
  • start  → spawn subprocess, write PID to <project_dir>/.pyhost.pid
  • stop   → kill by saved PID
  • restart→ stop + start
  • logs   → tail <project_dir>/.pyhost.log
  • stats  → read /proc/<pid> for RAM/CPU
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

import psutil

from config import PROJECTS_DIR, PLAN_LIMITS

log = logging.getLogger(__name__)

PID_FILE  = ".pyhost.pid"
LOG_FILE  = ".pyhost.log"


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
    with open(_pid_path(project_id), "w") as f:
        f.write(str(pid))


def _is_alive(pid: int) -> bool:
    try:
        proc = psutil.Process(pid)
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


class ProcessManager:
    """Manages user project subprocesses without Docker."""

    # ── Start ──────────────────────────────────────────────
    async def create_container(self, project_id: str, python_version: str,
                                plan: str = "free", port: Optional[int] = None) -> str:
        """Compatibility shim — just ensure project dir exists, return project_id."""
        os.makedirs(_project_dir(project_id), exist_ok=True)
        return project_id

    async def start_container(self, project_id: str, run_command: str,
                               env: Dict[str, str]) -> Tuple[bool, str]:
        """Launch run_command as a subprocess inside the project directory."""
        proj_dir = _project_dir(project_id)
        if not os.path.isdir(proj_dir):
            return False, f"project directory not found: {proj_dir}"

        # Stop any existing process first
        await self.stop_container(project_id)

        # Build full environment: inherit bot env + user vars
        full_env = os.environ.copy()
        full_env.update(env)

        # Choose the python binary for this version
        python_bin = _find_python(project_id, run_command)
        # Resolve the actual command — replace bare 'python' with full path
        cmd = run_command.strip()
        for alias in ("python3", "python"):
            if cmd.startswith(alias + " ") or cmd == alias:
                cmd = python_bin + cmd[len(alias):]
                break

        log_path = _log_path(project_id)
        try:
            with open(log_path, "a") as log_fp:
                log_fp.write(f"\n--- pyhost start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
                proc = subprocess.Popen(
                    cmd,
                    shell=True,
                    cwd=proj_dir,
                    env=full_env,
                    stdout=log_fp,
                    stderr=subprocess.STDOUT,
                    preexec_fn=os.setsid,   # new process group for clean kill
                )
            _write_pid(project_id, proc.pid)
            # Give it 1 second to fail fast
            await asyncio.sleep(1.0)
            if proc.poll() is not None:
                # Process already exited — read log tail for error
                tail = _tail_log(log_path, 20)
                return False, f"process exited immediately:\n{tail}"
            log.info("Started project %s PID=%d cmd=%r", project_id, proc.pid, cmd)
            return True, ""
        except Exception as exc:
            return False, str(exc)

    # ── Stop ───────────────────────────────────────────────
    async def stop_container(self, project_id: str) -> bool:
        pid = _read_pid(project_id)
        if pid is None:
            return False
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            await asyncio.sleep(0.5)
            if _is_alive(pid):
                os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass
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
            return {"ram_mb": 0, "cpu_percent": 0, "uptime_seconds": 0,
                    "status": "exited" if pid else "stopped"}
        try:
            proc = psutil.Process(pid)
            mem = proc.memory_info().rss / (1024 * 1024)
            cpu = proc.cpu_percent(interval=0.2)
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
            keep = [l for l in text.splitlines()
                    if any(kw in l.lower() for kw in
                           ("traceback", "error", "exception", "  file "))]
            text = "\n".join(keep) or "(no error lines found)"
        return text

    # ── Exec (for pip install) ─────────────────────────────
    async def exec_command(self, project_id: str, cmd: str,
                           workdir: str = "") -> Tuple[int, str]:
        proj_dir = _project_dir(project_id)
        cwd = workdir or proj_dir
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
            output = stdout.decode("utf-8", "ignore") if stdout else ""
            return proc.returncode or 0, output
        except asyncio.TimeoutError:
            return 1, "command timed out (300s)"
        except Exception as exc:
            return 1, str(exc)

    # ── is_alive helper ────────────────────────────────────
    def is_project_alive(self, project_id: str) -> bool:
        pid = _read_pid(project_id)
        return pid is not None and _is_alive(pid)

    # ── Admin helpers (compat shims) ───────────────────────
    async def list_pyhost_containers(self) -> List[Dict[str, Any]]:
        """Return running pyhost projects as pseudo-container list."""
        results = []
        try:
            if not os.path.isdir(PROJECTS_DIR):
                return []
            for pid_name in os.listdir(PROJECTS_DIR):
                proj_dir = os.path.join(PROJECTS_DIR, pid_name)
                pid_file = os.path.join(proj_dir, PID_FILE)
                if os.path.exists(pid_file):
                    pid = _read_pid(pid_name)
                    alive = pid is not None and _is_alive(pid)
                    results.append({
                        "id": pid_name[:12],
                        "name": f"pyhost_{pid_name}",
                        "status": "running" if alive else "exited",
                        "project_id": pid_name,
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

    # ── ping (compat) ──────────────────────────────────────
    def ping(self) -> bool:
        return True

    def _ensure_client(self) -> bool:
        return True


# ── Helpers ────────────────────────────────────────────────
def _tail_log(log_path: str, lines: int) -> str:
    try:
        with open(log_path, "rb") as f:
            # Efficient tail: seek from end
            f.seek(0, 2)
            size = f.tell()
            chunk = min(size, lines * 200)
            f.seek(-chunk, 2)
            raw = f.read()
        text = raw.decode("utf-8", "ignore")
        all_lines = text.splitlines()
        return "\n".join(all_lines[-lines:])
    except Exception as exc:
        return f"(log read error: {exc})"


def _find_python(project_id: str, run_command: str) -> str:
    """Find the best available python3 binary."""
    for candidate in ("python3.12", "python3.11", "python3.10", "python3", "python"):
        path = _which(candidate)
        if path:
            return path
    return "python3"


def _which(cmd: str) -> Optional[str]:
    import shutil
    return shutil.which(cmd)


# Singleton — drop-in replacement for docker_manager
process_manager = ProcessManager()
