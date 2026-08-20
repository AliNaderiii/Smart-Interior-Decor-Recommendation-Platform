"""Phase 2 (performance) regression tests.

These lock in behaviour that is easy to silently undo: the cache key must stay
user-scoped, concurrent misses must not stampede, and the HNSW recall knob must
stay configured. Each test guards a bug that was actually found in Phase 2.
"""
from __future__ import annotations

import threading
import time

from app.core.config import settings
from app.services.recommender import quiz_cache_key


QUIZ = {
    "styles": ["scandinavian"],
    "color_palette": ["#FFFFFF"],
    "materials": ["wood"],
    "patterns": [],
    "budget_min_toman": 1_000_000,
    "budget_max_toman": 50_000_000,
}


class TestCacheKeyScoping:
    def test_same_quiz_different_users_get_different_keys(self):
        """The v1 key was quiz-only, so identical answers shared one entry.

        The quiz is a handful of enumerated choices, so collisions between
        users are likely, and /recommend layers per-user Pro masking on top of
        the cached payload.
        """
        assert quiz_cache_key(QUIZ, "user-a") != quiz_cache_key(QUIZ, "user-b")

    def test_key_is_stable_for_same_user_and_quiz(self):
        assert quiz_cache_key(QUIZ, "user-a") == quiz_cache_key(QUIZ, "user-a")

    def test_key_ignores_dict_ordering(self):
        reordered = dict(reversed(list(QUIZ.items())))
        assert quiz_cache_key(QUIZ, "u") == quiz_cache_key(reordered, "u")

    def test_key_is_namespaced_by_user(self):
        assert quiz_cache_key(QUIZ, "user-a").startswith("rec:user-a:")

    def test_anonymous_key_stays_unscoped(self):
        """Internal/anonymous callers keep the shared key."""
        key = quiz_cache_key(QUIZ)
        assert key.startswith("rec:") and not key.startswith("rec:None")

    def test_different_quiz_same_user_differs(self):
        other = {**QUIZ, "styles": ["industrial"]}
        assert quiz_cache_key(QUIZ, "u") != quiz_cache_key(other, "u")


class TestSingleFlight:
    """A cold key hit by N concurrent callers must be computed once, not N times."""

    def test_concurrent_misses_compute_once(self, monkeypatch):
        import app.services.recommender as rec

        calls: list[float] = []

        def slow_compute(db, quiz, categories):
            calls.append(time.perf_counter())
            time.sleep(0.2)  # stand in for five pgvector searches
            return {"categories": {"sofa": []}, "cached": False}

        store: dict[str, bytes] = {}

        class FakeRedis:
            def get(self, k):
                return store.get(k)

            def setex(self, k, ttl, v):
                store[k] = v

        monkeypatch.setattr(rec, "_compute", slow_compute)
        monkeypatch.setattr(rec, "get_redis", lambda: FakeRedis())

        results: list[dict] = []

        def worker():
            results.append(rec.recommend(None, QUIZ, user_id="u1"))

        threads = [threading.Thread(target=worker) for _ in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 12
        # The whole point: 12 concurrent callers, one computation.
        assert len(calls) == 1, f"cache stampede: {len(calls)} concurrent computes"
        # Followers were served from the cache the leader populated.
        assert sum(1 for r in results if r.get("cached")) == 11

    def test_inflight_registry_is_drained(self, monkeypatch):
        """A leaked lock per key would be an unbounded memory leak."""
        import app.services.recommender as rec

        store: dict[str, bytes] = {}

        class FakeRedis:
            def get(self, k):
                return store.get(k)

            def setex(self, k, ttl, v):
                store[k] = v

        monkeypatch.setattr(rec, "_compute", lambda db, q, c: {"categories": {}, "cached": False})
        monkeypatch.setattr(rec, "get_redis", lambda: FakeRedis())
        rec._INFLIGHT.clear()
        rec.recommend(None, QUIZ, user_id="drain-test")
        assert rec._INFLIGHT == {}

    def test_compute_still_runs_when_cache_disabled(self, monkeypatch):
        import app.services.recommender as rec

        seen = []
        monkeypatch.setattr(
            rec, "_compute", lambda db, q, c: seen.append(1) or {"categories": {}, "cached": False}
        )
        monkeypatch.setattr(rec, "get_redis", lambda: None)
        rec.recommend(None, QUIZ, use_cache=False)
        assert seen == [1]


class TestHnswRecall:
    def test_ef_search_is_raised_above_pgvector_default(self):
        """Post-filtered ANN at the default ef_search=40 returned 14/100
        candidates on a 20.7k-row catalog — silent recall loss."""
        assert settings.HNSW_EF_SEARCH >= 400
