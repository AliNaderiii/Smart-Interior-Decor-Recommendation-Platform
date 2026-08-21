"""Stage 04 · recommender cache behaviour against a *real* Redis server.

The rest of the recommender suite runs on in-process fakeredis. These tests
exercise what only a real server can: actual TTL semantics, key eviction and
per-user cache isolation with real ``SETEX``/``GET`` round trips.

Set ``TEST_REDIS_URL`` to run (e.g. ``redis://127.0.0.1:6399/10``); the module
skips cleanly otherwise, mirroring ``tests/test_redis_real.py``.
"""
from __future__ import annotations

import os

import pytest

REDIS_URL = os.environ.get("TEST_REDIS_URL", "")

pytestmark = pytest.mark.skipif(
    not REDIS_URL, reason="set TEST_REDIS_URL to exercise a real Redis"
)


def make_quiz(**overrides) -> dict:
    quiz = {
        "styles": ["modern"],
        "color_palette": ["#2E2E2E"],
        "budget_min_toman": 1_000_000,
        "budget_max_toman": 150_000_000,
        "materials": ["wood"],
        "patterns": [],
    }
    quiz.update(overrides)
    return quiz


@pytest.fixture()
def real_redis(monkeypatch, reset_settings):
    import redis as redis_pkg

    from app.core import redis_client

    reset_settings(REDIS_URL=REDIS_URL, APP_ENV="test")
    client = redis_pkg.Redis.from_url(REDIS_URL, decode_responses=True)
    client.flushdb()
    monkeypatch.setattr(redis_client, "_client", client)
    yield client
    client.flushdb()


def test_real_redis_backend_is_redis(real_redis):
    assert "redis_version" in real_redis.info("server")


def test_recommend_cold_then_cached_hit(real_redis, db):
    from app.services.recommender import recommend

    quiz = make_quiz()
    first = recommend(db, quiz, user_id="redis-user-1")
    assert first["cached"] is False
    second = recommend(db, quiz, user_id="redis-user-1")
    assert second["cached"] is True
    assert second["categories"].keys() == first["categories"].keys()
    assert second["meta"]["weights_version"] == first["meta"]["weights_version"]


def test_cache_entry_has_real_ttl(real_redis, db):
    from app.services.recommender import recommend

    quiz = make_quiz(styles=["industrial"])
    recommend(db, quiz, user_id="redis-user-2")
    keys = real_redis.keys("rec:redis-user-2:*")
    assert keys, "cache key must exist on the real server"
    ttl = real_redis.ttl(keys[0])
    assert 0 < ttl <= 3600, f"TTL out of range: {ttl}"


def test_cache_is_per_user_on_real_server(real_redis, db):
    from app.services.recommender import recommend

    quiz = make_quiz(styles=["boho"])
    a = recommend(db, quiz, user_id="user-a")
    b = recommend(db, quiz, user_id="user-b")
    assert a["cached"] is False and b["cached"] is False
    assert len(real_redis.keys("rec:user-a:*")) == 1
    assert len(real_redis.keys("rec:user-b:*")) == 1


def test_feedback_signal_changes_cache_identity(real_redis, db):
    """A thumbs-down must not be served from the pre-feedback cached payload —
    feedback is part of the cache fingerprint by design."""
    from app.models.feedback import ProductFeedback
    from app.models.user import User
    from app.services.recommender import recommend

    # PostgreSQL enforces the FK that SQLite silently ignores in the dev suite
    user = User(email="fb-user@example.com", hashed_password="x", role="homeowner",
                full_name="FB User")
    db.add(user)
    db.commit()
    uid = user.id
    try:
        quiz = make_quiz()
        cold = recommend(db, quiz, user_id=uid)
        assert cold["cached"] is False
        assert recommend(db, quiz, user_id=uid)["cached"] is True

        sofa_id = next(iter(cold["categories"]["sofa"]))["id"]
        db.add(ProductFeedback(user_id=uid, product_id=sofa_id, signal=-1,
                               category="sofa"))
        db.commit()
        after = recommend(db, quiz, user_id=uid)
        assert after["cached"] is False, "feedback change must invalidate the cached entry"
        assert len(real_redis.keys(f"rec:{uid}:*")) >= 2
    finally:
        db.query(ProductFeedback).filter(ProductFeedback.user_id == uid).delete()
        db.query(User).filter(User.id == uid).delete()
        db.commit()
