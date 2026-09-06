"""ADR-014 — behavioural event stream (``POST /events``, admin summary).

Locks the spec's rules from ``docs/ai/feedback-events.md``:
write path never fails the user (202 with accepted/dropped), closed
vocabulary at the edge (422 for anything else), anonymous sessions allowed
but forged credentials still rejected, impressions are the denominator of
every rate, GDPR export/erasure cover the rows, and — explicitly — nothing in
the ranking pipeline reads the table.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.models.feedback_event import FeedbackEvent
from app.models.product import Product

URL = "/api/v1/events"


def _sid() -> str:
    return uuid.uuid4().hex


def _products(db, n=3):
    return db.scalars(
        select(Product).where(Product.is_verified.is_(True)).order_by(Product.id).limit(n)
    ).all()


def _batch(products, session_id=None, **overrides):
    events = [
        {"product_id": p.id, "event_type": "impression", "page_context": "recommend",
         "position": i + 1, "weights_version": "2026-09-06.1"}
        for i, p in enumerate(products)
    ]
    events.append({"product_id": products[0].id, "event_type": "click",
                   "page_context": "recommend", "position": 1})
    body = {"session_id": session_id or _sid(), "events": events}
    body.update(overrides)
    return body


# ---------------------------------------------------------------- ingest

def test_batch_is_accepted_and_persisted_with_category_denormalised(client, bearer_headers, db):
    prods = _products(db)
    sid = _sid()
    resp = client.post(URL, headers=bearer_headers, json=_batch(prods, sid))
    assert resp.status_code == 202, resp.text
    assert resp.json()["data"] == {"accepted": 4, "dropped": 0}
    rows = db.scalars(select(FeedbackEvent).where(FeedbackEvent.session_id == sid)).all()
    assert len(rows) == 4
    imp = [r for r in rows if r.event_type == "impression"]
    assert [r.position for r in sorted(imp, key=lambda r: r.position)] == [1, 2, 3]
    assert all(r.category == p.category for r, p in zip(sorted(imp, key=lambda r: r.position), prods))
    assert all(r.weights_version == "2026-09-06.1" for r in imp)
    assert all(r.user_id is not None for r in rows)


def test_anonymous_session_is_accepted_without_user(client, db):
    client.cookies.clear()
    prods = _products(db)
    sid = _sid()
    resp = client.post(URL, json=_batch(prods, sid))
    assert resp.status_code == 202, resp.text
    rows = db.scalars(select(FeedbackEvent).where(FeedbackEvent.session_id == sid)).all()
    assert rows and all(r.user_id is None for r in rows)


def test_forged_credentials_are_still_rejected(client, db):
    client.cookies.clear()
    resp = client.post(URL, headers={"Authorization": "Bearer not-a-token"}, json=_batch(_products(db)))
    assert resp.status_code == 401


def test_unknown_product_is_dropped_not_failed(client, bearer_headers, db):
    prods = _products(db, 1)
    body = _batch(prods)
    body["events"].append({"product_id": "does-not-exist", "event_type": "click", "page_context": "recommend"})
    resp = client.post(URL, headers=bearer_headers, json=body)
    assert resp.status_code == 202
    assert resp.json()["data"] == {"accepted": 2, "dropped": 1}


def test_closed_vocabulary_is_enforced_at_the_edge(client, bearer_headers, db):
    p = _products(db, 1)[0]
    bad = [
        {"product_id": p.id, "event_type": "hover", "page_context": "recommend"},
        {"product_id": p.id, "event_type": "click", "page_context": "email"},
        {"product_id": p.id, "event_type": "click", "page_context": "recommend", "note": "free text"},
        {"product_id": p.id, "event_type": "click", "page_context": "recommend", "position": 101},
    ]
    for event in bad:
        resp = client.post(URL, headers=bearer_headers, json={"session_id": _sid(), "events": [event]})
        assert resp.status_code == 422, event
    # session id must be 32 lowercase hex — no room for text
    resp = client.post(URL, headers=bearer_headers,
                       json={"session_id": "x" * 32, "events": [{"product_id": p.id, "event_type": "click", "page_context": "recommend"}]})
    assert resp.status_code == 422
    # empty and oversize batches
    assert client.post(URL, headers=bearer_headers, json={"session_id": _sid(), "events": []}).status_code == 422
    big = {"session_id": _sid(), "events": [{"product_id": p.id, "event_type": "impression", "page_context": "recommend"}] * 101}
    assert client.post(URL, headers=bearer_headers, json=big).status_code == 422


def test_rate_limited_per_subject(client, bearer_headers, db, reset_settings):
    reset_settings(EVENTS_RATE_LIMIT_PER_MINUTE=2)
    prods = _products(db, 1)
    codes = [client.post(URL, headers=bearer_headers, json=_batch(prods)).status_code for _ in range(3)]
    assert codes == [202, 202, 429]


# --------------------------------------------------------------- summary

def test_summary_requires_admin(client, bearer_headers):
    assert client.get("/api/v1/admin/events/summary", headers=bearer_headers).status_code == 403


def test_summary_reports_funnel_with_impressions_as_denominator(client, bearer_headers, admin_headers, db):
    prods = _products(db, 2)
    p0, p1 = prods
    sid = _sid()
    events = (
        [{"product_id": p0.id, "event_type": "impression", "page_context": "recommend", "position": 1}] * 10
        + [{"product_id": p0.id, "event_type": "click", "page_context": "recommend", "position": 1}] * 2
        + [{"product_id": p0.id, "event_type": "like", "page_context": "recommend", "position": 1}]
        + [{"product_id": p1.id, "event_type": "impression", "page_context": "recommend", "position": 2}] * 5
    )
    assert client.post(URL, headers=bearer_headers, json={"session_id": sid, "events": events}).status_code == 202

    data = client.get("/api/v1/admin/events/summary?days=1", headers=admin_headers).json()["data"]
    assert data["window_days"] == 1
    assert data["sessions"] >= 1 and data["total_events"] >= 18
    assert data["learning_ready"] is False and data["learning_threshold_events"] == 10_000
    cats = {c["category"]: c for c in data["categories"]}
    c0 = cats[p0.category]
    assert c0["impression"] >= 10 and c0["click"] >= 2 and c0["like"] >= 1
    assert c0["ctr"] is not None and 0 < c0["ctr"] <= 1
    assert c0["ctr"] == round(c0["click"] / c0["impression"], 4)
    assert data["totals"]["ctr"] == round(data["totals"]["click"] / data["totals"]["impression"], 4)


def test_summary_rates_are_null_without_impressions(client, bearer_headers, admin_headers, db, monkeypatch):
    """A rate without a denominator is exactly the artefact the spec forbids."""
    # Use a window that only sees this test's rows: isolate through a fresh
    # product category count by checking the invariant on every row instead.
    data = client.get("/api/v1/admin/events/summary?days=365", headers=admin_headers).json()["data"]
    for row in data["categories"] + [data["totals"]]:
        if row["impression"] == 0:
            assert row["ctr"] is None and row["like_rate"] is None
        else:
            assert row["ctr"] is not None


# -------------------------------------------------------------- GDPR

def test_export_includes_behavioural_events_and_erasure_unlinks_them(client, make_user, db):
    actor = make_user()
    uid = actor["user"]["id"]
    prods = _products(db, 1)
    sid = _sid()
    assert client.post(URL, headers=actor["headers"], json=_batch(prods, sid)).status_code == 202

    export = client.get("/api/v1/users/me/export", headers=actor["headers"]).json()["data"]
    assert "behavioural_events" in export
    assert {e["event_type"] for e in export["behavioural_events"]} == {"impression", "click"}
    assert all("note" not in e for e in export["behavioural_events"])

    assert client.delete("/api/v1/users/me", headers=actor["headers"]).status_code == 200
    db.expire_all()
    linked = db.scalar(select(func.count()).select_from(FeedbackEvent).where(FeedbackEvent.user_id == uid))
    assert linked == 0
    # the aggregate history survives, anonymised
    kept = db.scalars(select(FeedbackEvent).where(FeedbackEvent.session_id == sid)).all()
    assert len(kept) == 2 and all(r.user_id is None for r in kept)


# --------------------------------------------------- honesty guard

def test_ranking_pipeline_does_not_read_the_event_table():
    """The spec's §3 conditions are not met; no code may quietly 'learn' from
    events. Grep-level guard so a future change has to delete this test —
    and therefore write the ADR — first."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "app" / "services" / "recommender.py").read_text(encoding="utf-8")
    assert "FeedbackEvent" not in src and "feedback_events" not in src
