"""In-memory rate limiting + session caching (Redis-free replacement).

Drops the Redis dependency entirely. State is stored in plain Python
dicts and resets when the process restarts — which is fine for
rate limiting and short-lived session data.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from config import RATE_LIMIT_REQUESTS_PER_MIN, RATE_LIMIT_WINDOW_SEC

log = logging.getLogger(__name__)


class _InMemoryClient:
    """Mimics the RedisClient API without any Redis dependency."""

    def __init__(self) -> None:
        # rate limit store: {user_id: (count, window_start_epoch)}
        self._rl: dict[int, tuple[int, float]] = {}
        # session store: {key: (value_json, expire_epoch)}
        self._sess: dict[str, tuple[str, float]] = {}
        self._lock = asyncio.Lock()

    # ── Lifecycle (no-ops — kept for API compatibility) ────
    async def connect(self) -> "_InMemoryClient":
        log.info("In-memory store ready (Redis not used).")
        return self

    async def aclose(self) -> None:
        pass

    @property
    def client(self) -> "_InMemoryClient":
        return self

    # ── Rate limiting ──────────────────────────────────────
    async def is_rate_limited(self, user_id: int) -> bool:
        """True if user exceeded RATE_LIMIT_REQUESTS_PER_MIN in the window."""
        async with self._lock:
            now = time.monotonic()
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
