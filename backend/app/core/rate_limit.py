"""Redis-backed fixed-window rate limiter (abuse + AI cost control).

Applied to /recommend, /auth/login, /auth/register and — new in Stage 03 —
/products/upload, GET /share/{token} and the GDPR export endpoint. Each of
those either costs money (an embedding + a vector search, or an AI inference)
or exposes data to an unauthenticated caller.

Failure policy (Stage 03 — T-25)
--------------------------------
The v2 limiter failed **open**: any Redis error was logged and the request was
allowed. That is a defensible trade for a pure cost control and an indefensible
one for a security control, because it hands an attacker a two-step bypass —
knock Redis over (or simply wait for a failover), then brute-force freely, with
the outage itself masked as a warning line.

The behaviour is therefore environment-dependent and explicit:

* **production** — fail **closed**: `503` + `Retry-After`. Rejecting traffic
  while the throttle is blind is recoverable; silently disabling every
  authentication control is not.
* **development / test** — fail open, loudly logged, so a developer without
  Redis is never blocked.

Because production also refuses to boot without ``REDIS_URL`` and refuses a
fakeredis client, "Redis is unavailable" in production means a genuine outage,
not a missing configuration.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)

#: Returned when the throttle cannot be evaluated in production.
THROTTLE_UNAVAILABLE_RETRY_AFTER = 5


def _fail(exc: Exception, key: str) -> None:
    """Apply the environment's failure policy for an unusable throttle."""
    if settings.is_production:
        logger.error(
            "rate limiter unavailable (%s) for key=%s; failing CLOSED", exc, key
        )
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Service temporarily unavailable, please retry",
            headers={"Retry-After": str(THROTTLE_UNAVAILABLE_RETRY_AFTER)},
        )
    logger.warning(
        "rate limiter unavailable (%s) for key=%s; failing open (APP_ENV=%s)",
        exc, key, settings.APP_ENV,
    )


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
    bucket = f"rl:{key}"
    try:
        redis = get_redis()
        current = redis.incr(bucket)
        if current == 1:
            redis.expire(bucket, window_seconds)
        if current > limit:
            ttl = max(int(redis.ttl(bucket) or window_seconds), 1)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Rate limit exceeded ({limit} per {window_seconds}s). "
                f"Retry in {ttl}s.",
                # V2: machine-readable backoff, not just prose in the body.
                headers={"Retry-After": str(ttl)},
            )
    except HTTPException:
        raise
    except Exception as exc:
        _fail(exc, key)
