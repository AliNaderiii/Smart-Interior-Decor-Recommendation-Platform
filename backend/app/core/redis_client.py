"""Redis client factory.

Uses a real Redis when ``REDIS_URL`` is set (docker-compose / production);
falls back to an in-process fakeredis instance for local development and
tests so the suite never needs network access.

Stage 03 (T-26): the fallback is now **refused in production**. Previously an
empty ``REDIS_URL`` in production silently produced a per-worker fakeredis, so
every rate limit and brute-force lockout became "limit x number of workers" and
nothing was shared. `Settings.validate_runtime()` already rejects that
configuration at boot; this is the second lock, covering the case where the
client is constructed from a code path that never validated (a script, a
background worker, a test that patched settings).
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: Any = None


class RedisUnavailable(RuntimeError):
    """Production asked for a shared Redis and there is none."""


def get_redis() -> Any:
    global _client
    if _client is not None:
        return _client
    if settings.REDIS_URL:
        import redis

        _client = redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            # Bound every call: a hung Redis must not hang the request thread.
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
            health_check_interval=30,
        )
    else:
        if settings.is_production:
            raise RedisUnavailable(
                "REDIS_URL is empty in production. fakeredis is per-process, so "
                "rate limits, brute-force lockouts and the refresh-token "
                "blacklist would not be shared between workers."
            )
        import fakeredis

        logger.info("Using in-process fakeredis (APP_ENV=%s)", settings.APP_ENV)
        _client = fakeredis.FakeRedis(decode_responses=True)
    return _client


def is_shared_backend() -> bool:
    """True when the client is a real, cross-process Redis."""
    return bool(settings.REDIS_URL)


def ping() -> bool:
    """Cheap liveness probe used by the fail-closed throttles."""
    try:
        return bool(get_redis().ping())
    except Exception as exc:
        logger.warning("redis ping failed: %s", exc)
        return False


def reset_redis_for_tests() -> None:
    global _client
    _client = None
