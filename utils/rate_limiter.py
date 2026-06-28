"""Thin convenience wrapper over redis_client.is_rate_limited."""
from __future__ import annotations

from database.redis_client import redis_client


async def is_rate_limited(user_id: int) -> bool:
    return await redis_client.is_rate_limited(user_id)


async def ttl(user_id: int) -> int:
    return await redis_client.rate_limit_ttl(user_id)
