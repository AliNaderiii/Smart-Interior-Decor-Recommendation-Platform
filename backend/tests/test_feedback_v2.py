"""Phase 3: 👍/👎 feedback must persist AND change the next result set.

A thumbs button that only sets local state is the definition of a dead key
(RESEARCH_V2 §2), so these tests assert the full round-trip: the API records
the verdict, and the recommender demotes the disliked product.
"""
from __future__ import annotations

from sqlalchemy import select

from app.models.product import Product
from app.services.recommender import (
    FEEDBACK_BOOST,
    FEEDBACK_PENALTY,
    apply_feedback,
    load_feedback,
)

API = "/api/v1"


def _first_product_id(db) -> str:
    """Straight from the DB — GET /products is admin-only, and these tests run
    as an ordinary homeowner."""
    pid = db.execute(select(Product.id).limit(1)).scalar_one_or_none()
    assert pid, "seed data missing"
    return pid


class TestFeedbackApi:
    def test_thumbs_up_is_persisted(self, client, bearer_headers, db):
        pid = _first_product_id(db)
        r = client.post(f"{API}/feedback", headers=bearer_headers,
                        json={"product_id": pid, "signal": 1})
        assert r.status_code == 201, r.text
        assert r.json()["data"]["signal"] == 1

        listed = client.get(f"{API}/feedback", headers=bearer_headers)
        assert listed.json()["data"][pid] == 1

    def test_opposite_thumb_overwrites(self, client, bearer_headers, db):
        pid = _first_product_id(db)
        client.post(f"{API}/feedback", headers=bearer_headers,
                    json={"product_id": pid, "signal": 1})
        client.post(f"{API}/feedback", headers=bearer_headers,
                    json={"product_id": pid, "signal": -1})
        listed = client.get(f"{API}/feedback", headers=bearer_headers)
        # Overwrite, not a second row.
        assert listed.json()["data"] == {pid: -1}

    def test_same_thumb_twice_toggles_off(self, client, bearer_headers, db):
        """The UI renders a pressed state, so a second click must un-press it —
        otherwise a mis-click is permanent."""
        pid = _first_product_id(db)
        client.post(f"{API}/feedback", headers=bearer_headers,
                    json={"product_id": pid, "signal": 1})
        r = client.post(f"{API}/feedback", headers=bearer_headers,
                        json={"product_id": pid, "signal": 1})
        assert r.json()["data"]["signal"] == 0
        assert client.get(f"{API}/feedback", headers=bearer_headers).json()["data"] == {}

    def test_unknown_product_404s(self, client, bearer_headers):
        r = client.post(f"{API}/feedback", headers=bearer_headers,
                        json={"product_id": "does-not-exist", "signal": 1})
        assert r.status_code == 404

    def test_invalid_signal_is_rejected(self, client, bearer_headers, db):
        pid = _first_product_id(db)
        for bad in (0, 5, -2, "up"):
            r = client.post(f"{API}/feedback", headers=bearer_headers,
                            json={"product_id": pid, "signal": bad})
            assert r.status_code == 422, f"signal={bad!r} should be rejected"

    def test_unknown_field_rejected(self, client, bearer_headers, db):
        pid = _first_product_id(db)
        r = client.post(f"{API}/feedback", headers=bearer_headers,
                        json={"product_id": pid, "signal": 1, "admin": True})
        assert r.status_code == 422

    def test_requires_auth(self, client):
        r = client.post(f"{API}/feedback", json={"product_id": "x", "signal": 1})
        assert r.status_code in (401, 403)

    def test_feedback_is_per_user(self, client, bearer_headers, admin_headers, db):
        """One user's verdicts must never leak into another's."""
        pid = _first_product_id(db)
        client.post(f"{API}/feedback", headers=bearer_headers,
                    json={"product_id": pid, "signal": -1})
        other = client.get(f"{API}/feedback", headers=admin_headers)
        assert pid not in other.json()["data"]

    def test_clear_resets_everything(self, client, bearer_headers, db):
        pid = _first_product_id(db)
        client.post(f"{API}/feedback", headers=bearer_headers,
                    json={"product_id": pid, "signal": 1})
        assert client.delete(f"{API}/feedback", headers=bearer_headers).status_code == 204
        assert client.get(f"{API}/feedback", headers=bearer_headers).json()["data"] == {}


class TestReRanking:
    def test_dislike_demotes_below_neutral(self):
        ranked = [
            {"id": "a", "final_score": 0.90},
            {"id": "b", "final_score": 0.85},
            {"id": "c", "final_score": 0.80},
        ]
        out = apply_feedback(ranked, {"a": -1})
        assert out[-1]["id"] == "a", "disliked item must fall to the bottom"
        assert out[0]["id"] == "b"

    def test_like_boosts(self):
        ranked = [
            {"id": "a", "final_score": 0.90},
            {"id": "b", "final_score": 0.85},
        ]
        out = apply_feedback(ranked, {"b": 1})
        assert out[0]["id"] == "b"
        assert out[0]["feedback"] == 1

    def test_penalty_outweighs_boost(self):
        """A dislike is a stronger signal than a like — asymmetric by design."""
        assert FEEDBACK_PENALTY > FEEDBACK_BOOST

    def test_scores_stay_in_range(self):
        ranked = [{"id": "a", "final_score": 0.98}, {"id": "b", "final_score": 0.05}]
        out = apply_feedback(ranked, {"a": 1, "b": -1})
        for row in out:
            assert 0.0 <= row["final_score"] <= 1.0

    def test_no_feedback_is_a_noop(self):
        ranked = [{"id": "a", "final_score": 0.9}, {"id": "b", "final_score": 0.8}]
        assert apply_feedback(list(ranked), {}) == ranked

    def test_load_feedback_anonymous_is_empty(self, db):
        assert load_feedback(db, None) == {}


class TestRecommendIntegration:
    def test_thumbs_down_changes_recommendations(self, client, bearer_headers, db):
        """End-to-end: the cached payload must not mask the new signal."""
        quiz = {
            "styles": ["scandinavian"], "color_palette": ["#FFFFFF"],
            "room_width_cm": 400, "room_length_cm": 500,
            "budget_min_toman": 1_000_000, "budget_max_toman": 90_000_000,
            "materials": ["wood"], "patterns": [],
        }
        q = client.post(f"{API}/quiz", headers=bearer_headers, json=quiz)
        assert q.status_code == 201, q.text
        qid = q.json()["data"]["id"]

        first = client.post(f"{API}/recommend?quiz_id={qid}", headers=bearer_headers)
        assert first.status_code == 200, first.text
        cats = first.json()["data"]["categories"]
        cat = next(c for c, items in cats.items() if len(items) >= 2)
        top_id = cats[cat][0]["id"]

        client.post(f"{API}/feedback", headers=bearer_headers,
                    json={"product_id": top_id, "signal": -1})

        second = client.post(f"{API}/recommend?quiz_id={qid}", headers=bearer_headers)
        new_items = second.json()["data"]["categories"][cat]
        new_ids = [i["id"] for i in new_items]
        # Either demoted within the page or pushed off it entirely.
        assert new_ids[0] != top_id, "feedback did not change the ranking (cache bleed?)"
