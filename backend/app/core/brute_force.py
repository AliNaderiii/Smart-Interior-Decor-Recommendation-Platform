"""Brute-force login protection (OWASP A07 — Authentication Failures).

Phase 0B probe: eight consecutive wrong-password logins all returned 401 and
were never throttled (`docs/SECURITY_AUDIT_V2.md` §A07). This module adds a
Redis-backed lockout.

Policy
------
* Counter key is ``login_fail:{ip}:{email}`` — scoped to the *pair*, so one
  attacker cannot lock a victim out of their own account from a different IP
  (that would turn the defence into a DoS), while still stopping a single
  source from spraying one account.
* ``MAX_ATTEMPTS`` (5) failures within ``WINDOW`` ⇒ blocked for ``BLOCK`` (15 min).
* A successful login clears the counter.
* Responses carry a real ``Retry-After`` header, not just prose in the body.
* Fails **open** if Redis is unavailable: availability beats throttling, and
  the event is logged loudly.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, status

from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 15 * 60
BLOCK_SECONDS = 15 * 60


def _key(ip: str, email: str) -> str:
    return f"login_fail:{ip}:{email.lower()}"


def _block_key(ip: str, email: str) -> str:
    return f"login_block:{ip}:{email.lower()}"


def check_not_blocked(ip: str, email: str) -> None:
    """Raise 429 (with Retry-After) when this ip+email pair is locked out."""
    try:
        redis = get_redis()
        ttl = redis.ttl(_block_key(ip, email))
    except Exception as exc:  # Redis down -> fail open
        logger.warning("brute-force check unavailable (%s); failing open", exc)
        return
    if ttl and ttl > 0:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many failed login attempts. Try again in {ttl}s.",
            headers={"Retry-After": str(ttl)},
        )


def register_failure(ip: str, email: str) -> int:
    """Count one failed attempt; engage the block on the Nth. Returns count."""
    try:
        redis = get_redis()
        key = _key(ip, email)
        count = int(redis.incr(key))
        if count == 1:
            redis.expire(key, WINDOW_SECONDS)
        if count >= MAX_ATTEMPTS:
            redis.setex(_block_key(ip, email), BLOCK_SECONDS, "1")
            redis.delete(key)
            logger.warning(
                "brute-force lockout engaged for email=%s ip=%s after %d attempts",
                email, ip, count,
            )
        return count
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("brute-force counter unavailable (%s)", exc)
        return 0


def reset(ip: str, email: str) -> None:
    """Clear counters after a successful authentication."""
    try:
        redis = get_redis()
        redis.delete(_key(ip, email))
        redis.delete(_block_key(ip, email))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("brute-force reset failed (%s)", exc)


def remaining_attempts(ip: str, email: str) -> int:
    try:
        count = int(get_redis().get(_key(ip, email)) or 0)
    except Exception:
        return MAX_ATTEMPTS
    return max(0, MAX_ATTEMPTS - count)
