"""ADR-016 · catalog-integrity gate — policy, persistence, enforcement.

What is proven here (each class = one enforcement point):

* ``ai.catalog_integrity`` is a pure, deterministic policy: the exact failure
  found on the live catalog on 2026-09-07 (a "rug" whose picture was a sofa,
  made of metal and leather, titled «فرش modern», linked to a marketplace root)
  produces the expected codes, and a clean row produces none;
* the two-tier semantics: truth-tier codes block everywhere, sellability
  codes only in strict (production) mode;
* the recommender and visual search exclude ``integrity_ok = False`` rows and
  keep ``NULL`` (legacy, not yet backfilled) rows;
* ``POST /products/{id}/verify`` refuses a failing row with 409 + reasons,
  ``?force=true`` overrides with an audit record and a visible marker;
* the seed scripts stamp provenance, produce category-consistent rows, and
  refuse to write synthetic rows in production;
* the CI audit script exits non-zero on a failing verified row.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from ai import catalog_integrity as policy
from app.models.audit_log import AuditLog
from app.models.product import Product
from app.services import catalog_integrity as service
from app.services import recommender, visual_search

PRODUCTS = "/api/v1/products"


@pytest.fixture(autouse=True)
def _no_outbound_link_checks(monkeypatch):
    """The routes schedule a real HEAD against the seller host after every
    write; this module is about the gate, not the network."""
    import app.api.routes.products as routes

    monkeypatch.setattr(routes, "check_product_link", lambda product_id: None)


_API_CREATED: list[str] = []


@pytest.fixture(autouse=True, scope="module")
def _remove_api_created_rows():
    """Rows written through the HTTP surface are committed outside the
    conftest rollback isolation. On PostgreSQL (CI) the database outlives the
    run and pytest is invoked more than once per job, so delete them here
    instead of letting verified test rugs accumulate in the shared catalog."""
    yield
    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        for pid in _API_CREATED:
            row = session.get(Product, pid)
            if row is not None:
                session.delete(row)
        session.commit()
    finally:
        session.close()

# The row the 2026-09-07 live probe returned for the "rug" category.
LIVE_BAD_RUG = {
    "id": "live-rug",
    "title": "Contemporary Modern Rug — Black Metal",
    "title_fa": "فرش modern",
    "category": "rug",
    "price_toman": 22_000_000,
    "image_url": "https://images.unsplash.com/photo-1631679706909-1844bbd07221?w=800&q=70&fm=webp",
    "seller_link": "https://www.digikala.com/",
    "materials": ["metal", "leather"],
    "width_cm": 200, "depth_cm": 150, "height_cm": 1,
    "extraction_raw": {"source": "synthetic-demo", "detected_category": "sofa"},
    "source": "synthetic-demo",
}

CLEAN_ROW = {
    "id": "clean-1",
    "title": "Hand-knotted Tabriz wool rug 200x300",
    "title_fa": "فرش دستباف تبریز پشمی ۲۰۰×۳۰۰",
    "category": "rug",
    "price_toman": 48_000_000,
    "image_url": "https://cdn.example-seller.ir/media/rugs/tabriz-200x300.jpg",
    "image_phash": "a1b2c3d4e5f60718",
    "seller_link": "https://www.digikala.com/product/dkp-1234567/فرش-تبریز/",
    "link_status": "ok",
    "materials": ["fabric"],
    "width_cm": 300, "depth_cm": 200, "height_cm": 1,
    "price_checked_at": datetime.now(timezone.utc) - timedelta(days=2),
    "extraction_raw": {"detected_category": "rug"},
    "source": "feed:example-seller",
}


def _product(**overrides) -> Product:
    base = dict(
        title="Nordic sofa", title_fa="مبل راحتی سه‌نفره نوردیک", category="sofa",
        room_type="living_room", price_toman=45_000_000,
        image_url=f"https://cdn.example.ir/p/{uuid.uuid4().hex}.jpg",
        seller_link=f"https://www.digikala.com/product/dkp-{uuid.uuid4().hex[:7]}/sofa/",
        colors=["#E0D5C1"], styles=["modern"], materials=["wood", "fabric"], patterns=["solid"],
        width_cm=210, depth_cm=90, height_cm=80, description="a modern sofa",
        extraction_confidence=0.9, extraction_raw={"detected_category": "sofa"},
        is_verified=True, source="manual",
        price_checked_at=datetime.now(timezone.utc),
    )
    base.update(overrides)
    p = Product(**base)
    from ai.embedding_service import get_embedding, product_to_text

    p.style_embedding = get_embedding(product_to_text(
        p.title, p.styles, p.colors, p.materials, p.description, p.patterns
    ))
    return p


# --------------------------------------------------------------------- policy

class TestPolicy:
    def test_live_bad_rug_fails_the_truth_tier_for_the_right_reasons(self):
        decision = policy.integrity_decision(LIVE_BAD_RUG, strict=False)
        assert decision["ok"] is False
        assert {"image_category_mismatch", "material_implausible", "title_fa_invalid"} <= set(decision["reasons"])
        # sellability codes are advisories outside production
        assert {"synthetic_row", "seller_link_shallow", "price_stale"} <= set(decision["advisories"])
        assert not set(decision["reasons"]) & policy.PRODUCTION_BLOCKING

    def test_live_bad_rug_fails_harder_in_strict_mode(self):
        decision = policy.integrity_decision(LIVE_BAD_RUG, strict=True)
        assert decision["ok"] is False
        assert {"synthetic_row", "seller_link_shallow", "price_stale"} <= set(decision["reasons"])
        assert decision["advisories"] == []

    def test_clean_row_passes_both_tiers(self):
        for strict in (False, True):
            decision = policy.integrity_decision(CLEAN_ROW, strict=strict)
            assert decision == {
                "ok": True, "reasons": [], "advisories": [], "checks": [],
                "strict": strict, "policy_version": policy.INTEGRITY_POLICY_VERSION,
            }, decision

    def test_tiers_are_disjoint_and_cover_every_documented_code(self):
        assert not policy.ALWAYS_BLOCKING & policy.PRODUCTION_BLOCKING
        assert set(policy.INTEGRITY_REASON_TEXT) == policy.ALL_CODES | {policy.ADMIN_OVERRIDE}
        for code, text in policy.INTEGRITY_REASON_TEXT.items():
            assert text["en"] and text["fa"], code

    @pytest.mark.parametrize("url,depth", [
        (None, "missing"), ("", "missing"), ("   ", "missing"),
        ("https://www.digikala.com/", "shallow"),
        ("https://www.digikala.com/main/home-and-kitchen/", "shallow"),
        ("https://torob.com/browse/1029/مبلمان/", "shallow"),
        ("https://www.digikala.com/search/category-home-decoration/", "shallow"),
        ("https://basalam.com/vendor-x", "deep"),
        ("https://www.digikala.com/product/dkp-1234567/", "deep"),
        ("https://torob.com/p/abcdef12-3456/فرش-ماشینی/", "deep"),
    ])
    def test_seller_link_depth(self, url, depth):
        assert policy.seller_link_depth(url) == depth

    @pytest.mark.parametrize("title,problem", [
        (None, "title_fa_missing"), ("", "title_fa_missing"),
        ("Modern Sofa", "title_fa_invalid"),          # no Persian letters
        ("فرش modern", "title_fa_invalid"),           # the live bug: bare template token
        ("صندلی راحتی industrial", "title_fa_invalid"),  # same template, more Persian words
        ("چراغ lighting", "title_fa_invalid"),
        ("مبل sofa سه نفره", "title_fa_invalid"),
        ("مبل راحتی مدل Modern", None),               # a real listing: Latin word introduced by «مدل»
        ("کوسن مخمل طرح Boho", None),
        ("مبل راحتی سه‌نفره مدل L", None),            # a stray Latin model letter is fine
        ("فرش دستباف تبریز", None),
    ])
    def test_title_fa_problem(self, title, problem):
        assert policy.title_fa_problem(title) == problem

    def test_image_key_prefers_phash_and_ignores_query_string(self):
        a = policy.image_key("https://images.unsplash.com/photo-1?w=800", None)
        b = policy.image_key("https://images.unsplash.com/photo-1?w=1200&q=90", None)
        assert a == b == "url:images.unsplash.com/photo-1"
        assert policy.image_key("https://x/y.jpg", "ABCD") == "phash:abcd"
        assert policy.image_key(None, None) is None

    def test_duplicate_image_ignores_self_and_flags_others(self):
        key = policy.image_key(CLEAN_ROW["image_url"], CLEAN_ROW["image_phash"])
        assert "duplicate_image" not in policy.integrity_checks(CLEAN_ROW, known_images={key: {"clean-1"}})
        assert "duplicate_image" in policy.integrity_checks(CLEAN_ROW, known_images={key: {"clean-1", "other"}})

    def test_dimensions_price_and_materials_bands(self):
        row = dict(CLEAN_ROW, height_cm=95)  # a 95 cm tall rug
        assert "dimensions_out_of_band" in policy.integrity_checks(row)
        row = dict(CLEAN_ROW, width_cm=0, depth_cm=None)  # unknown dims are not checked
        assert "dimensions_out_of_band" not in policy.integrity_checks(row)
        row = dict(CLEAN_ROW, price_toman=1)  # an upload draft
        assert "price_out_of_band" in policy.integrity_checks(row)
        row = dict(CLEAN_ROW, materials=["glass"])
        assert "material_implausible" in policy.integrity_checks(row)
        row = dict(CLEAN_ROW, materials=[])  # nothing listed = nothing to contradict
        assert "material_implausible" not in policy.integrity_checks(row)

    def test_price_staleness_uses_the_reference_clock(self):
        now = datetime(2026, 9, 7, tzinfo=timezone.utc)
        fresh = dict(CLEAN_ROW, price_checked_at=now - timedelta(days=policy.PRICE_MAX_AGE_DAYS))
        stale = dict(CLEAN_ROW, price_checked_at=now - timedelta(days=policy.PRICE_MAX_AGE_DAYS + 1))
        naive = dict(CLEAN_ROW, price_checked_at=(now - timedelta(days=1)).replace(tzinfo=None))
        assert "price_stale" not in policy.integrity_checks(fresh, now=now)
        assert "price_stale" in policy.integrity_checks(stale, now=now)
        assert "price_stale" not in policy.integrity_checks(naive, now=now)
        assert "price_stale" in policy.integrity_checks(dict(CLEAN_ROW, price_checked_at=None), now=now)

    def test_detected_category_other_or_missing_never_mismatches(self):
        for raw in ({}, {"detected_category": None}, {"detected_category": "other"}, {"detected_category": "  "}):
            assert "image_category_mismatch" not in policy.integrity_checks(dict(CLEAN_ROW, extraction_raw=raw))

    def test_dead_or_unsafe_seller_link_is_a_truth_failure(self):
        for status in ("dead", "unsafe"):
            codes = policy.integrity_checks(dict(CLEAN_ROW, link_status=status))
            assert "seller_link_dead" in codes and "seller_link_dead" in policy.ALWAYS_BLOCKING
        for status in ("ok", "redirect", "blocked", "error", None):
            assert "seller_link_dead" not in policy.integrity_checks(dict(CLEAN_ROW, link_status=status))

    def test_realistic_dataset_rows_count_as_synthetic(self):
        row = dict(CLEAN_ROW, source="manual", extraction_raw={"source": "realistic_dataset_v3"})
        assert policy.is_synthetic(row)
        row = dict(CLEAN_ROW, source="manual", extraction_raw={"dataset_notice": "sample"})
        assert policy.is_synthetic(row)
        assert not policy.is_synthetic(CLEAN_ROW)

    def test_observed_failures_fold_in_and_unknown_codes_are_dropped(self):
        codes = policy.integrity_checks(CLEAN_ROW, observed=["image_unreachable", "not_a_code"])
        assert codes == ["image_unreachable"]

    def test_describe_is_bilingual(self):
        en = policy.describe(["synthetic_row"])
        fa = policy.describe(["synthetic_row"], lang="fa")
        assert en[0].startswith("synthetic_row: demo/benchmark row")
        assert "نمونه" in fa[0]
        assert policy.describe(["mystery"]) == ["mystery"]


# --------------------------------------------------------- service + persistence

class TestServiceStamping:
    def test_refresh_stamps_row_and_strict_follows_app_env(self, db, reset_settings):
        p = _product(source="synthetic-demo", extraction_raw={"source": "synthetic-demo", "detected_category": "sofa"})
        db.add(p)
        db.flush()
        reset_settings(APP_ENV="test")
        decision = service.refresh(p, db)
        assert decision["strict"] is False and p.integrity_ok is True
        assert p.integrity_reasons == [] and p.integrity_checked_at is not None

        reset_settings(APP_ENV="production")
        decision = service.refresh(p, db)
        assert decision["strict"] is True and p.integrity_ok is False
        assert "synthetic_row" in p.integrity_reasons

    def test_keep_override_survives_reevaluation(self, db):
        p = _product(materials=["glass"], category="rug", width_cm=200, depth_cm=150, height_cm=1,
                     extraction_raw={"detected_category": "rug"}, title_fa="فرش شیشه‌ای هنری")
        db.add(p)
        db.flush()
        first = service.refresh(p, db, strict=False)
        assert p.integrity_ok is False and "material_implausible" in first["reasons"]
        service.force_override(p, first)
        assert p.integrity_ok is True and policy.ADMIN_OVERRIDE in p.integrity_reasons
        service.refresh(p, db, strict=False, keep_override=True)  # e.g. a title edit
        assert p.integrity_ok is True and policy.ADMIN_OVERRIDE in p.integrity_reasons
        service.refresh(p, db, strict=False, keep_override=False)  # backfill --reset-overrides
        assert p.integrity_ok is False and policy.ADMIN_OVERRIDE not in p.integrity_reasons

    def test_image_index_folds_in_unsaved_rows(self, db):
        url = f"https://cdn.example.ir/dup/{uuid.uuid4().hex}.jpg"
        a, b = _product(image_url=url), _product(image_url=url)
        db.add_all([a, b])
        db.flush()
        index = service.image_index(db, [a, b])
        assert index[policy.image_key(url)] == {a.id, b.id}
        assert "duplicate_image" in service.evaluate(a, known_images=index, strict=True)["reasons"]

    def test_summary_counts_verified_rows_only(self, db):
        before = service.summary(db)
        assert before["policy_version"] == policy.INTEGRITY_POLICY_VERSION
        db.add(_product(is_verified=False, integrity_ok=False, integrity_reasons=["synthetic_row"]))
        db.flush()
        after = service.summary(db)
        assert after["reason_counts"] == before["reason_counts"]  # unverified rows do not count


# ----------------------------------------------------------- runtime exclusion

QUIZ = {
    "styles": ["modern"], "color_palette": ["#E0D5C1"],
    "room_width_cm": 400, "room_length_cm": 500,
    "budget_min_toman": 44_000_000, "budget_max_toman": 46_000_000,
    "materials": ["wood"], "patterns": ["solid"],
}


def _recommended_ids(db, category="sofa"):
    result = recommender.recommend(db, QUIZ, categories=[category], use_cache=False)
    return {p["id"] for items in result["categories"].values() for p in items}, result["meta"]


class TestRecommenderExclusion:
    def test_excluded_rows_never_reach_the_ranking_but_null_and_true_do(self, db):
        ok = _product(title="ok sofa", integrity_ok=True)
        legacy = _product(title="legacy sofa", integrity_ok=None)
        bad = _product(title="bad sofa", integrity_ok=False, integrity_reasons=["image_category_mismatch"])
        db.add_all([ok, legacy, bad])
        db.flush()
        ids, meta = _recommended_ids(db)
        assert ok.id in ids and legacy.id in ids
        assert bad.id not in ids, "an integrity-failed row leaked into recommendations"
        quality = meta["catalog_quality"]["sofa"]
        assert quality["excluded"] >= 1 and quality["eligible"] >= 2

    def test_card_payload_carries_provenance(self, db):
        p = _product(title="feed sofa", source="feed:demo-seller", integrity_ok=True)
        db.add(p)
        db.flush()
        ids, _ = _recommended_ids(db)
        assert p.id in ids
        payload = recommender._product_payload(p)
        assert payload["source"] == "feed:demo-seller"
        assert payload["integrity_ok"] is True
        assert payload["price_checked_at"].startswith(str(datetime.now(timezone.utc).year))

    def test_visual_search_candidates_skip_excluded_rows(self, db):
        bad = _product(title="bad visual", integrity_ok=False)
        db.add(bad)
        db.flush()
        query = visual_search.VisualQuery(palette=[], mode="palette", embedding=None)
        candidates = visual_search._candidates(db, "sofa", query)
        assert bad.id not in {p.id for p, _ in candidates}

    def test_config_version_bump_invalidates_pre_gate_cache_entries(self, db):
        from ai.model_registry import RECOMMENDER_CONFIG_VERSION

        assert RECOMMENDER_CONFIG_VERSION == "2026-09-07.1"
        assert recommender.CONFIG["config_version"] == RECOMMENDER_CONFIG_VERSION
        # The cache fingerprint carries the config version, so a payload cached
        # under 2026-09-06.1 (pre-gate Stage A) can never be served now.
        old = recommender.quiz_cache_key({**QUIZ, "_categories": ["sofa"], "_cfg": "2026-09-06.1"})
        new = recommender.quiz_cache_key({**QUIZ, "_categories": ["sofa"], "_cfg": RECOMMENDER_CONFIG_VERSION})
        assert old != new
        result = recommender.recommend(db, QUIZ, categories=["sofa"], use_cache=False)
        assert result["meta"]["weights_version"] == RECOMMENDER_CONFIG_VERSION


# --------------------------------------------------------- admin verify (HTTP)

def _create_via_api(client, headers, **overrides):
    body = {
        "title": "Hand-entered rug", "title_fa": "فرش دستباف کاشان",
        "category": "rug", "price_toman": 30_000_000,
        "image_url": f"https://cdn.example.ir/api/{uuid.uuid4().hex}.jpg",
        "seller_link": "https://www.digikala.com/product/dkp-7654321/فرش/",
        "colors": ["#8B0000"], "styles": ["classic"], "materials": ["fabric"], "patterns": ["persian"],
        "width_cm": 300, "depth_cm": 200, "height_cm": 1,
    }
    body.update(overrides)
    resp = client.post(PRODUCTS, headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    _API_CREATED.append(data["id"])
    return data


class TestAdminVerifyGate:
    def test_create_evaluates_integrity_and_exposes_it(self, client, admin_headers):
        data = _create_via_api(client, admin_headers, materials=["metal"])
        assert data["source"] == "manual"
        assert data["integrity_ok"] is False
        assert "material_implausible" in data["integrity_reasons"]

    def test_verify_refuses_failing_row_with_409_and_reasons(self, client, admin_headers, db):
        data = _create_via_api(client, admin_headers, materials=["metal"])
        resp = client.post(f"{PRODUCTS}/{data['id']}/verify", headers=admin_headers)
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body["success"] is False
        # the envelope's ``error`` is a string: machine codes in brackets first
        assert body["error"].startswith("catalog integrity failed [")
        assert "material_implausible" in body["error"]
        assert db.get(Product, data["id"]).is_verified is False

    def test_patch_cannot_sidestep_the_gate(self, client, admin_headers, db):
        data = _create_via_api(client, admin_headers, materials=["metal"])
        resp = client.patch(f"{PRODUCTS}/{data['id']}", headers=admin_headers, json={"is_verified": True})
        assert resp.status_code == 409, resp.text
        assert db.get(Product, data["id"]).is_verified is False

    def test_fixing_the_row_then_verifying_succeeds(self, client, admin_headers, db):
        data = _create_via_api(client, admin_headers, materials=["metal"])
        fixed = client.patch(f"{PRODUCTS}/{data['id']}", headers=admin_headers, json={"materials": ["fabric"]})
        assert fixed.status_code == 200 and fixed.json()["data"]["integrity_ok"] is True
        resp = client.post(f"{PRODUCTS}/{data['id']}/verify", headers=admin_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"] == {
            "id": data["id"], "is_verified": True, "integrity_ok": True, "integrity_reasons": [],
        }

    def test_force_override_is_audited_and_visible(self, client, admin_headers, db):
        data = _create_via_api(client, admin_headers, materials=["metal"])
        resp = client.post(f"{PRODUCTS}/{data['id']}/verify?force=true", headers=admin_headers)
        assert resp.status_code == 200, resp.text
        out = resp.json()["data"]
        assert out["is_verified"] is True and out["integrity_ok"] is True
        assert out["integrity_reasons"][-1] == policy.ADMIN_OVERRIDE
        assert "material_implausible" in out["integrity_reasons"]
        db.expire_all()
        row = db.get(Product, data["id"])
        assert row.is_verified is True and row.integrity_ok is True
        log = db.scalars(
            select(AuditLog).where(AuditLog.detail.like(f"%product={data['id']}%")).order_by(AuditLog.created_at.desc())
        ).first()
        assert log is not None and "FORCED" in log.detail and "material_implausible" in log.detail

    def test_unverify_is_audited_and_flushes_the_recommendation_cache(self, client, admin_headers, db, monkeypatch):
        """P4-ب·2f: the 2026-09-11 chair pilot verified three rows a decor
        recommender must not show; the admin takes them out with
        ``PATCH {is_verified: false}`` — attributable, and the cached
        ``/recommend`` payloads that may still list them are dropped."""
        from app.api.routes import products as route
        from app.models.audit_log import ACTION_PRODUCT_UNVERIFY

        flushed: list[int] = []
        monkeypatch.setattr(route, "flush_recommendation_cache", lambda: flushed.append(1) or 1)
        data = _create_via_api(client, admin_headers)
        assert client.post(f"{PRODUCTS}/{data['id']}/verify", headers=admin_headers).status_code == 200
        resp = client.patch(f"{PRODUCTS}/{data['id']}", headers=admin_headers, json={"is_verified": False})
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["is_verified"] is False
        db.expire_all()
        assert db.get(Product, data["id"]).is_verified is False
        log = db.scalars(select(AuditLog).where(AuditLog.action == ACTION_PRODUCT_UNVERIFY)
                         .order_by(AuditLog.created_at.desc())).first()
        assert log is not None and f"product={data['id']}" in log.detail
        assert flushed == [1]
        # idempotent: un-verifying an already unverified row is a no-op for audit and cache
        resp = client.patch(f"{PRODUCTS}/{data['id']}", headers=admin_headers, json={"is_verified": False})
        assert resp.status_code == 200 and flushed == [1]
        # a plain field edit does not touch verification, audit or cache
        resp = client.patch(f"{PRODUCTS}/{data['id']}", headers=admin_headers, json={"description": "x"})
        assert resp.status_code == 200 and flushed == [1]

    def test_unverify_works_on_a_row_that_fails_integrity(self, client, admin_headers, db):
        # a verified row can always be pulled back — the gate only guards the way *in*
        data = _create_via_api(client, admin_headers)
        assert client.post(f"{PRODUCTS}/{data['id']}/verify", headers=admin_headers).status_code == 200
        resp = client.patch(f"{PRODUCTS}/{data['id']}", headers=admin_headers,
                            json={"is_verified": False, "materials": ["metal"]})
        assert resp.status_code == 200, resp.text
        out = resp.json()["data"]
        assert out["is_verified"] is False and out["integrity_ok"] is False

    def test_price_edit_refreshes_price_checked_at(self, client, admin_headers):
        data = _create_via_api(client, admin_headers)
        assert data["price_checked_at"] is None
        resp = client.patch(f"{PRODUCTS}/{data['id']}", headers=admin_headers, json={"price_toman": 31_000_000})
        assert resp.status_code == 200 and resp.json()["data"]["price_checked_at"] is not None

    def test_admin_stats_reports_integrity(self, client, admin_headers):
        resp = client.get("/api/v1/admin/stats", headers=admin_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert "integrity_excluded_products" in data
        assert data["catalog_integrity"]["policy_version"] == policy.INTEGRITY_POLICY_VERSION
        assert data["catalog_integrity"]["strict"] is False


# --------------------------------------------------------------- p6 extraction

class TestDetectedCategoryPlumbing:
    def test_mock_provider_reports_what_the_filename_says(self):
        from ai.feature_extractor import MockProvider

        assert MockProvider.detect_category("07-industrial-iron-bookshelf.png") == "storage"
        assert MockProvider.detect_category("boho-kilim-rug.jpg") == "rug"
        assert MockProvider.detect_category("walnut-coffee-table.jpg") == "coffee_table"
        assert MockProvider.detect_category("velvet-armchair.jpg") == "chair"
        assert MockProvider.detect_category("blob.png") is None

    def test_sanitizer_accepts_only_taxonomy_values(self):
        from ai.feature_extractor import _sanitize

        assert _sanitize({"detected_category": "Rug"})["detected_category"] == "rug"
        assert _sanitize({"detected_category": ["storage"]})["detected_category"] == "storage"
        assert _sanitize({"detected_category": "other"})["detected_category"] == "other"
        assert _sanitize({"detected_category": "bed"})["detected_category"] is None
        assert _sanitize({})["detected_category"] is None

    def test_prompt_p6_asks_for_the_field(self):
        from ai import feature_extractor as fe

        assert fe.EXTRACTION_PROMPT_VERSION == "p6"
        assert '"detected_category"' in fe.EXTRACTION_PROMPT and '"other"' in fe.EXTRACTION_PROMPT

    def test_review_decision_flags_mismatch_only_with_a_known_claim(self):
        from ai.extraction_review import review_decision

        payload = {"confidence": 0.95, "style": ["boho"], "provider": "gemini", "detected_category": "sofa"}
        assert "category_mismatch" not in review_decision(payload)["review_reasons"]
        assert "category_mismatch" not in review_decision(payload, expected_category="sofa")["review_reasons"]
        flagged = review_decision(payload, expected_category="rug")
        assert "category_mismatch" in flagged["review_reasons"] and flagged["needs_review"] is True
        other = dict(payload, detected_category="other")
        assert "category_mismatch" not in review_decision(other, expected_category="rug")["review_reasons"]

    def test_upload_uses_detected_category_and_hashes_the_image(self, client, admin_headers, db):
        import io

        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (32, 24), (200, 40, 40)).save(buf, format="PNG")
        resp = client.post(
            f"{PRODUCTS}/upload", headers=admin_headers,
            files={"file": ("boho-linen-kilim-rug.png", buf.getvalue(), "image/png")},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert data["product"]["category"] == "rug"
        assert data["extraction"]["detected_category"] == "rug"
        row = db.get(Product, data["product"]["id"])
        try:
            assert row.image_phash and len(row.image_phash) == 16
            assert row.extraction_raw["detected_category"] == "rug"
            assert row.materials == ["fabric"]
            assert row.integrity_ok is True  # 1-toman draft price is a strict-tier advisory only
        finally:
            db.delete(row)
            db.commit()


# ------------------------------------------------------------------ seed scripts

class TestSeedScripts:
    def test_synthetic_seed_rows_are_category_consistent_and_stamped(self):
        from scripts.seed_products import PHOTO_IDS_BY_CATEGORY, build_products

        products = build_products()
        assert len(products) == 100
        index: dict[str, set[str]] = {}
        for p in products:
            key = policy.image_key(p.image_url)
            index.setdefault(key, set()).add(p.id or p.title)
        for p in products:
            assert p.source == "synthetic-demo"
            assert p.extraction_raw["detected_category"] == p.category
            photo_id = p.image_url.split("/photo-")[1].split("?")[0]
            assert photo_id in PHOTO_IDS_BY_CATEGORY[p.category], (p.category, photo_id)
            decision = policy.integrity_decision(p, strict=False)
            assert decision["ok"], (p.title, decision["reasons"])
            assert "synthetic_row" in policy.integrity_decision(p, strict=True)["reasons"]
        assert {p.category for p in products} == set(PHOTO_IDS_BY_CATEGORY)

    def test_no_photo_id_is_shared_across_seed_categories(self):
        from scripts.seed_products import PHOTO_IDS_BY_CATEGORY

        seen: dict[str, str] = {}
        for category, ids in PHOTO_IDS_BY_CATEGORY.items():
            for pid in ids:
                assert seen.setdefault(pid, category) == category, pid

    def test_realistic_dataset_has_no_cross_category_images(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        for rel in ("datasets/products_realistic.json", "datasets/products_realistic_150.json",
                    "backend/seed_data/products_realistic_150.json"):
            rows = json.loads((root / rel).read_text(encoding="utf-8"))
            by_image: dict[str, set[str]] = {}
            for r in rows:
                by_image.setdefault(policy.image_key(r["image_url"]), set()).add(r["category"])
            shared = {k: v for k, v in by_image.items() if len(v) > 1}
            assert not shared, (rel, shared)
            assert not any("1532372320572" in k for k in by_image), f"{rel}: dead photo id still referenced"

    def test_loader_rows_pass_truth_tier_and_are_marked_synthetic(self):
        from scripts.load_realistic_products import read_products, to_model

        rows = read_products(expand_to=150)
        for row in rows:
            model = to_model(row, {})
            assert model.source == "synthetic-demo"
            assert model.extraction_raw["detected_category"] == model.category
            decision = policy.integrity_decision(model, strict=False)
            assert decision["ok"], (row["id"], decision["reasons"])

    def test_seed_products_refuses_production_without_the_flag(self, tmp_path):
        import os
        import subprocess
        import sys
        from pathlib import Path

        backend = Path(__file__).resolve().parents[1]
        env = dict(os.environ)
        env.update({
            "APP_ENV": "production", "SECRET_KEY": "p" * 48,
            "REDIS_URL": "redis://127.0.0.1:6399/15", "COOKIE_SECURE": "true",
            "FRONTEND_ORIGIN": "https://app.example.com",
            "AI_PROVIDER": "mock", "EMBEDDING_BACKEND": "hash",
            "STORAGE_BACKEND": "local", "PAYMENT_PROVIDER": "mock",
            "DATABASE_URL": f"sqlite:///{tmp_path / 'prod.sqlite3'}",
            "LOCAL_STORAGE_DIR": str(tmp_path / "storage"),
        })
        env.pop("SEED_DEMO_ACCOUNTS", None)
        proc = subprocess.run(
            [sys.executable, "scripts/seed_products.py"], cwd=backend, env=env,
            capture_output=True, text=True, timeout=600,
        )
        assert proc.returncode == 0, proc.stderr[-2000:]  # fail-safe, not fail-loud (start commands)
        assert "REFUSING to seed synthetic demo products" in proc.stderr
        import sqlite3

        con = sqlite3.connect(tmp_path / "prod.sqlite3")
        try:
            assert con.execute("select count(*) from products").fetchone()[0] == 0
        finally:
            con.close()


# ------------------------------------------------------------------ audit script

class TestAuditScript:
    def test_audit_reports_and_exits_nonzero_on_failing_verified_rows(self):
        from scripts.audit_catalog import audit

        report = audit([dict(CLEAN_ROW, is_verified=True), dict(LIVE_BAD_RUG, is_verified=True)], strict=False)
        assert report["verified_failing"] == 1
        assert report["by_category"]["rug"] == {"total": 2, "verified": 2, "eligible": 1, "excluded": 1}
        assert report["failing"][0]["id"] == "live-rug"
        assert report["reason_counts"]["image_category_mismatch"] == 1
        assert report["advisory_counts"]["synthetic_row"] == 1

    def test_audit_cli_on_a_catalog_file(self, tmp_path, capsys):
        from scripts.audit_catalog import main

        good = tmp_path / "good.json"
        good.write_text(json.dumps([{
            "id": "f1", "title_fa": "فرش کاشان", "title_en": "Kashan rug", "category": "rug",
            "price_toman": 20_000_000, "image_url": "https://cdn.x.ir/a.jpg",
            "seller_link": "https://www.digikala.com/product/dkp-1/", "material_tags": ["fabric"],
            "dimensions_cm": {"length": 300, "width": 200, "height": 1},
        }]), encoding="utf-8")
        assert main(["--file", str(good), "--json"]) == 0
        report = json.loads(capsys.readouterr().out)
        assert report["verified_failing"] == 0 and report["rows"] == 1
        # strict: price never checked -> fails the production tier
        assert main(["--file", str(good), "--strict"]) == 1
        assert "price_stale" in capsys.readouterr().out
