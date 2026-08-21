"""Stage 03 · behaviour against a *real*, shared Redis (work item 9, T-27).

The rest of the suite runs on in-process fakeredis, which cannot show the two
things that actually matter in production:

* **shared state** — two workers must see one counter. With fakeredis each
  worker has its own, so "5 attempts per 15 minutes" silently becomes
  "5 x workers".
* **real command semantics** — `INCR`/`EXPIRE`/`TTL`/`SETEX`, key eviction and
  atomicity behave differently in a real server than in an emulator.

Set ``TEST_REDIS_URL`` to run these; the module skips cleanly otherwise so CI
without a Redis service is not red for the wrong reason. Evidence from a real
run (redislite 6.2.14) is in
``docs/agent-reports/security-hardening-evidence/``.
"""
from __future__ import annotations

import os
import time
import uuid

import pytest

REDIS_URL = os.environ.get("TEST_REDIS_URL", "")

pytestmark = pytest.mark.skipif(
    not REDIS_URL, reason="set TEST_REDIS_URL to exercise a real Redis")


@pytest.fixture()
def real_redis(monkeypatch, reset_settings):
    """Point the whole application at a real Redis for one test."""
    import redis as redis_pkg

    from app.core import brute_force, rate_limit, redis_client

    reset_settings(REDIS_URL=REDIS_URL, APP_ENV="test")
    client = redis_pkg.Redis.from_url(REDIS_URL, decode_responses=True)
    client.flushdb()
    monkeypatch.setattr(redis_client, "_client", client)
    monkeypatch.setattr(rate_limit, "get_redis", lambda: client)
    monkeypatch.setattr(brute_force, "get_redis", lambda: client)
    yield client
    client.flushdb()


def test_the_backend_is_actually_redis(real_redis):
    info = real_redis.info("server")
    assert "redis_version" in info
    assert real_redis.ping() is True


def test_the_counter_is_shared_between_two_independent_clients(real_redis):
    """The property fakeredis cannot demonstrate."""
    import redis as redis_pkg

    from app.core.rate_limit import enforce_rate_limit

    key = f"shared:{uuid.uuid4().hex}"
    enforce_rate_limit(key, limit=10)
    enforce_rate_limit(key, limit=10)

    # A *second*, independent connection — the stand-in for a second worker.
    other = redis_pkg.Redis.from_url(REDIS_URL, decode_responses=True)
    assert other.get(f"rl:{key}") == "2", (
        "the second worker cannot see the first worker's counter"
    )


def test_rate_limit_window_expires_for_real(real_redis):
    from fastapi import HTTPException

    from app.core.rate_limit import enforce_rate_limit

    key = f"win:{uuid.uuid4().hex}"
    enforce_rate_limit(key, limit=1, window_seconds=1)
    with pytest.raises(HTTPException) as err:
        enforce_rate_limit(key, limit=1, window_seconds=1)
    assert err.value.status_code == 429
    assert int(err.value.headers["Retry-After"]) >= 1

    time.sleep(1.2)
    enforce_rate_limit(key, limit=1, window_seconds=1)  # window rolled over


def test_ttl_is_set_on_the_first_increment(real_redis):
    from app.core.rate_limit import enforce_rate_limit

    key = f"ttl:{uuid.uuid4().hex}"
    enforce_rate_limit(key, limit=5, window_seconds=60)
    ttl = real_redis.ttl(f"rl:{key}")
    assert 0 < ttl <= 60, f"bucket would never expire (ttl={ttl})"


def test_brute_force_lockout_is_shared_and_expires(real_redis):
    from fastapi import HTTPException

    from app.core import brute_force

    ip, email = "203.0.113.7", f"{uuid.uuid4().hex[:8]}@example.com"
    for _ in range(brute_force.MAX_ATTEMPTS):
        brute_force.register_failure(ip, email)

    with pytest.raises(HTTPException) as err:
        brute_force.check_not_blocked(ip, email)
    assert err.value.status_code == 429
    assert err.value.headers.get("Retry-After")

    keys = list(real_redis.scan_iter("login_block:*"))
    assert keys, "the lockout is not visible to other workers"
    for key in keys:
        assert real_redis.ttl(key) > 0, f"{key} would never expire"


def test_reset_clears_the_lockout(real_redis):
    from app.core import brute_force

    ip, email = "203.0.113.8", f"{uuid.uuid4().hex[:8]}@example.com"
    for _ in range(3):
        brute_force.register_failure(ip, email)
    brute_force.reset(ip, email)
    brute_force.check_not_blocked(ip, email)  # must not raise
    assert brute_force.remaining_attempts(ip, email) == brute_force.MAX_ATTEMPTS


def test_refresh_token_blacklist_survives_in_a_shared_store(real_redis, client,
                                                            demo_user):
    """A token revoked on worker A must be rejected by worker B."""
    import redis as redis_pkg

    login = client.post("/api/v1/auth/login", json=demo_user)
    assert login.status_code == 200, login.text
    refresh_token = login.json()["data"]["refresh_token"]

    rotated = client.post("/api/v1/auth/refresh",
                          json={"refresh_token": refresh_token})
    assert rotated.status_code == 200, rotated.text

    other = redis_pkg.Redis.from_url(REDIS_URL, decode_responses=True)
    blacklisted = list(other.scan_iter("blacklist:*"))
    assert blacklisted, "the revocation never reached the shared store"
    for key in blacklisted:
        assert other.ttl(key) > 0, "a blacklist entry without a TTL leaks memory"

    replay = client.post("/api/v1/auth/refresh",
                         json={"refresh_token": refresh_token})
    assert replay.status_code == 401


def test_login_lockout_end_to_end_against_real_redis(real_redis, client,
                                                     demo_user, reset_settings):
    reset_settings(LOGIN_RATE_LIMIT_PER_MINUTE=1000)
    codes = [
        client.post("/api/v1/auth/login",
                    json={"email": demo_user["email"], "password": "wrong"}).status_code
        for _ in range(6)
    ]
    assert 429 in codes, codes
    blocked = client.post("/api/v1/auth/login", json=demo_user)
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After")
