"""Redis-backed fixed-window rate limiter (AI cost control).

Applied to /recommend (20 req/min per user by default): each request costs an
embedding + a vector search, so an abusive client could inflate AI/DB spend.
Uses the shared Redis client (fakeredis in dev/test), fails open if Redis is
down — availability beats throttling for an MVP.

NOTE: with multiple uvicorn workers and the fakeredis dev fallback, each
worker keeps its own in-process counter (limit becomes ~N_workers x limit).
Production sets REDIS_URL, giving one shared counter across workers.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)


def enforce_rate_limit(key: str, limit: int | None = None,
                       window_seconds: int = 60) -> None:
    """Raise 429 when `key` exceeds `limit` calls per `window_seconds`.

    `limit` defaults to settings.RECOMMEND_RATE_LIMIT_PER_MINUTE; 0 disables
    (used by load tests / trusted internal callers).
    """
    if limit is None:
        limit = settings.RECOMMEND_RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return
    redis = get_redis()
    bucket = f"rl:{key}"
    try:
        current = redis.incr(bucket)
        if current == 1:
            redis.expire(bucket, window_seconds)
        if current > limit:
            ttl = max(int(redis.ttl(bucket) or window_seconds), 1)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Rate limit exceeded ({limit}/min). Retry in {ttl}s.",
                # V2: machine-readable backoff, not just prose in the body.
                headers={"Retry-After": str(ttl)},
            )
    except HTTPException:
        raise
    except Exception as exc:  # Redis down -> fail open
        logger.warning("rate limiter unavailable (%s); failing open", exc)
