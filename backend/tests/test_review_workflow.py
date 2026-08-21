"""Stage 04 remediation · human-review workflow audit (proof, not claims).

Independent review asked whether flagged extractions are *operationally*
reviewable. This module proves, end-to-end through the real HTTP surface:

* ``needs_review`` / ``review_reasons`` are **persisted** (inside
  ``products.extraction_raw``) together with provider/model/version stamps;
* every uploaded product starts ``is_verified=False`` — even a
  high-confidence auto-accept still waits for explicit human approval;
* unapproved products **cannot enter recommendations** (Stage A hard-filters
  ``is_verified``), and appear in the admin-only ``GET /products?is_verified=
  false`` list (paginated) until an admin approves them via ``PATCH``;
* after approval the product enters recommendations normally.

What this module deliberately does NOT claim: a dedicated review queue
(filter by ``needs_review``/``review_reasons``, one-click reprocess) does not
exist yet — that remains **IR-AI-002 (Medium)** in ``integration-request.md``.

Environment: APP_ENV=test (mock provider is allowed outside production; its
results are labelled ``provider="mock"`` and are never presented as
vision-model accuracy).
"""
from __future__ import annotations

import io

import pytest
from PIL import Image
from sqlalchemy import select

from app.models.product import Product
from app.services import recommender

UPLOAD = "/api/v1/products/upload"
PRODUCTS = "/api/v1/products"


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (24, 18), (10, 120, 200)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _remove_uploaded_drafts():
    """Delete the 1-toman draft rows this module commits via the HTTP surface.

    The upload endpoint prices drafts at 1 toman and commits through its own
    session (outside the conftest rollback isolation). Without this cleanup
    those rows persist and later no-result tests (impossible-budget windows)
    legitimately find a matching product and fail.
    """
    yield
    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        for row in session.query(Product).filter(Product.price_toman == 1).all():
            session.delete(row)
        session.commit()
    finally:
        session.close()


def _upload(client, headers, filename):
    resp = client.post(
        UPLOAD, headers=headers,
        files={"file": (filename, _png(), "image/png")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


QUIZ = {
    "styles": ["modern"],
    "color_palette": ["#1A1A1A"],
    "room_width_cm": 400,
    "room_length_cm": 500,
    "budget_min_toman": 0,
    # The upload route prices drafts at 1 toman, so a tiny budget window
    # isolates the uploaded product from the seeded catalog's prices and makes
    # recommendation membership deterministic (no ranking-cutoff flakiness).
    "budget_max_toman": 1_000,
    "materials": ["wood"],
    "patterns": ["solid"],
}


class TestFlaggedExtractionPersistence:
    def test_low_confidence_upload_is_flagged_and_persisted(
        self, client, admin_headers, db
    ):
        # "blob.png" carries no taxonomy keywords: the honest mock provider
        # yields 0.6 confidence -> below the 0.80 auto-accept bar -> flagged.
        data = _upload(client, admin_headers, "blob.png")
        extraction = data["extraction"]
        assert extraction["needs_review"] is True
        assert "low_confidence" in extraction["review_reasons"]

        product = db.get(Product, data["product"]["id"])
        assert product is not None and product.is_verified is False
        # persisted for the reviewer, with provenance stamps:
        raw = product.extraction_raw
        assert raw["needs_review"] is True
        assert "low_confidence" in raw["review_reasons"]
        assert raw["provider"] == "mock"
        assert raw["taxonomy_version"] and raw["prompt_version"]

    def test_high_confidence_upload_still_requires_human_approval(
        self, client, admin_headers, db
    ):
        # Both style and material keywords present -> mock confidence 0.9 ->
        # auto-accept *eligibility*, but is_verified stays False until a human
        # signs off. "Auto-accept" is not "auto-verified".
        data = _upload(client, admin_headers, "07-industrial-iron-bookshelf.png")
        assert data["extraction"]["needs_review"] is False
        product = db.get(Product, data["product"]["id"])
        assert product.is_verified is False


class TestQuarantineUntilApproval:
    def test_unapproved_product_is_hidden_from_recommendations_and_listed_for_review(
        self, client, admin_headers, db
    ):
        data = _upload(client, admin_headers, "07-industrial-iron-bookshelf.png")
        pid = data["product"]["id"]

        # visible in the admin unverified queue (paginated, filterable):
        queue = client.get(
            f"{PRODUCTS}?is_verified=false&page=1&page_size=10", headers=admin_headers
        )
        assert queue.status_code == 200
        body = queue.json()["data"]
        assert body["page"] == 1 and body["page_size"] == 10  # pagination surface
        assert pid in [item["id"] for item in body["items"]]

        # NOT visible to shoppers:
        verified = client.get(
            f"{PRODUCTS}?is_verified=true", headers=admin_headers
        ).json()["data"]
        assert pid not in [item["id"] for item in verified["items"]]

        result = recommender.recommend(db, QUIZ, categories=["sofa"], use_cache=False)
        ids = {
            p["id"]
            for items in result["categories"].values()
            for p in items
        } if isinstance(result.get("categories"), dict) else set()
        assert pid not in ids, "unverified product leaked into recommendations"

    def test_approval_via_patch_releases_product_into_recommendations(
        self, client, admin_headers, db
    ):
        data = _upload(client, admin_headers, "07-industrial-iron-bookshelf.png")
        pid = data["product"]["id"]

        before = recommender.recommend(
            db, QUIZ, categories=["sofa"], use_cache=False
        )
        flat_before = {
            p["id"]
            for items in before["categories"].values()
            for p in items
        }
        assert pid not in flat_before

        resp = client.patch(
            f"{PRODUCTS}/{pid}", headers=admin_headers, json={"is_verified": True}
        )
        assert resp.status_code == 200, resp.text

        after = recommender.recommend(
            db, QUIZ, categories=["sofa"], use_cache=False
        )
        flat_after = {
            p["id"]
            for items in after["categories"].values()
            for p in items
        }
        assert pid in flat_after, "approved product did not enter recommendations"

    def test_review_gate_cannot_be_bypassed_by_direct_product_creation(
        self, client, admin_headers, db
    ):
        # POST /products does not even accept is_verified in the payload —
        # verification is not an input, it is an admin action.
        resp = client.post(
            PRODUCTS, headers=admin_headers,
            json={
                "title": "hand-entered sofa",
                "category": "sofa",
                "price_toman": 10_000_000,
                "image_url": "https://example.com/sofa.jpg",
                "colors": ["#1A1A1A"],
                "styles": ["modern"],
                "materials": ["wood"],
                "patterns": ["solid"],
                "is_verified": True,  # must be rejected outright
            },
        )
        assert resp.status_code == 422, resp.text
        payload = resp.json()
        details = payload.get("details") or []
        assert any(
            "is_verified" in str(d.get("field", "")) or "is_verified" in str(d)
            for d in details
        ) or "is_verified" in str(payload), payload
        row = db.scalar(
            select(Product).where(Product.title == "hand-entered sofa")
        )
        assert row is None
