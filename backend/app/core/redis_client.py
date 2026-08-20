"""Redis client factory.

Uses a real Redis when ``REDIS_URL`` is set (docker-compose / production);
falls back to an in-process fakeredis instance for local development and
tests so the suite never needs network access.
"""
from __future__ import annotations

from typing import Any

from app.core.config import settings

_client: Any = None


def get_redis() -> Any:
    global _client
    if _client is not None:
        return _client
    if settings.REDIS_URL:
        import redis

        _client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    else:
        import fakeredis

        _client = fakeredis.FakeRedis(decode_responses=True)
    return _client


def reset_redis_for_tests() -> None:
    global _client
    _client = None
