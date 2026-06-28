"""In-memory rate limiting + session caching (Redis-free replacement).

WARNING: This is intentionally in-memory only. State is stored in plain
Python dicts and resets when the process restarts, so rate limits and
session data are not durable across deploys or crashes.

BUG-033: For multi-instance deployments behind a load balancer, each
process maintains its OWN rate-limit counters, so a single user can
effectively call N x RATE_LIMIT_REQUESTS_PER_MIN per minute (N = number
of bot replicas).  This file logs a loud warning every time it is
imported and again when the connect() lifecycle hook fires.  Operators
should replace this shim with a real Redis-backed implementation before
running more than one bot replica.

BUG-051: this file uses lowercase generic syntax (``dict[int, ...]``)
which is PEP 585 / Python 3.9+.  Combined with ``from __future__ import
annotations`` at the top, all annotations are strings, so the syntax is
fine on every supported runtime.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, Tuple

from config import RATE_LIMIT_REQUESTS_PER_MIN, RATE_LIMIT_WINDOW_SEC

log = logging.getLogger(__name__)


class _InMemoryClient:
    """Mimics the RedisClient API without any Redis dependency."""

    def __init__(self) -> None:
        # WARNING: in-memory only; all state is lost on process restart.
        # TODO: migrate both stores to Redis for multi-process durability.
        # rate limit store: {user_id: (count, window_start_epoch)}
        self._rl: Dict[int, Tuple[int, float]] = {}
        # session store: {key: (value_json, expire_epoch)}
        self._sess: Dict[str, Tuple[str, float]] = {}
        self._lock = asyncio.Lock()

    # ── Lifecycle (no-ops — kept for API compatibility) ────
    async def connect(self) -> "_InMemoryClient":
        # BUG-033: explicit warning so multi-instance deployments cannot
        # silently double up on per-user rate limits.
        log.warning(
            "Using in-memory rate/session store only; data resets on restart "
            "and is NOT shared across processes.  Multi-instance deployments "
            "MUST switch to a Redis-backed implementation to avoid bypassed "
            "rate limits."
        )
        return self

    async def aclose(self) -> None:
        pass

    @property
    def client(self) -> "_InMemoryClient":
        return self

    # Once the rate-limit dict grows past this many entries, prune the
    # stale ones (windows older than 2x the window). Prevents unbounded
    # memory growth — one entry per user_id would otherwise live forever.
    _RL_CLEANUP_THRESHOLD = 10000

    def _cleanup_rate_limits(self) -> None:
        """Drop rate-limit entries whose window has long expired."""
        if len(self._rl) <= self._RL_CLEANUP_THRESHOLD:
            return
        now = time.monotonic()
        self._rl = {
            uid: (c, ws)
            for uid, (c, ws) in self._rl.items()
            if now - ws < RATE_LIMIT_WINDOW_SEC * 2
        }
        log.debug("rate-limit dict pruned to %d entries", len(self._rl))

    # ── Rate limiting ──────────────────────────────────────
    async def is_rate_limited(self, user_id: int) -> bool:
        """True if user exceeded RATE_LIMIT_REQUESTS_PER_MIN in the window."""
        async with self._lock:
            now = time.monotonic()
            # Periodic cleanup to prevent unbounded memory growth.
            self._cleanup_rate_limits()
            count, window_start = self._rl.get(user_id, (0, now))
            if now - window_start >= RATE_LIMIT_WINDOW_SEC:
                # Window expired — reset
                count, window_start = 0, now
            count += 1
            self._rl[user_id] = (count, window_start)
            return count > RATE_LIMIT_REQUESTS_PER_MIN

    async def rate_limit_ttl(self, user_id: int) -> int:
        async with self._lock:
            now = time.monotonic()
            count, window_start = self._rl.get(user_id, (0, now))
            remaining = RATE_LIMIT_WINDOW_SEC - (now - window_start)
            return max(int(remaining), 0)

    # ── Session caching (per-user conversation state) ──────
    @staticmethod
    def _skey(user_id: int, key: str) -> str:
        return f"sess:{user_id}:{key}"

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, (_, exp) in self._sess.items() if exp <= now]
        for k in expired:
            del self._sess[k]

    async def set_session(self, user_id: int, key: str, value: Any, ttl: int = 300) -> None:
        async with self._lock:
            self._evict_expired()
            self._sess[self._skey(user_id, key)] = (
                json.dumps(value),
                time.monotonic() + ttl,
            )

    async def get_session(self, user_id: int, key: str) -> Any:
        async with self._lock:
            entry = self._sess.get(self._skey(user_id, key))
            if entry is None:
                return None
            val_json, exp = entry
            if time.monotonic() > exp:
                del self._sess[self._skey(user_id, key)]
                return None
            try:
                return json.loads(val_json)
            except Exception:
                return val_json

    async def del_session(self, user_id: int, key: str) -> None:
        async with self._lock:
            self._sess.pop(self._skey(user_id, key), None)

    async def clear_session(self, user_id: int) -> None:
        async with self._lock:
            prefix = f"sess:{user_id}:"
            to_del = [k for k in self._sess if k.startswith(prefix)]
            for k in to_del:
                del self._sess[k]


redis_client = _InMemoryClient()


async def close_redis() -> None:
    await redis_client.aclose()
    log.info("In-memory store closed.")
