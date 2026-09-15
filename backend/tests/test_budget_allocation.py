"""ADR-019 — the quiz budget is the living-room TOTAL, split per category.

Pins the contract in five layers:

1. ``allocate_budget`` math (pure): full set = configured shares, a single
   category = the whole window, a subset renormalises, ``per_item`` = legacy,
   integers only, monotone in the total.
2. Config validation: the ``budget`` section is a boot contract like the
   weights — missing section, unknown mode, missing category, min-share sum
   ≠ 1, max-share sum < 1 all refuse to load with a readable sentence.
3. Engine: Stage A filters and the budget component scores with the
   category window (a 900k cushion and a 3M lamp are recommendable for a
   60–150M total; a 19M rug is NOT for a 20M total); ``meta.budget_allocation``
   echoes the windows; explanation fidelity still reconstructs the score.
4. Cache identity: the mode is part of the key even when defaulted.
5. HTTP: ``budget_mode`` is optional and validated on ``POST /recommend``;
   the payload carries the allocation.
"""
from __future__ import annotations

import json
import uuid

import pytest

from app.models.product import CATEGORIES, Product
from app.services import recommender as rec
from app.services.recommender import (
    BUDGET_MODES,
    BUDGET_SHARES,
    allocate_budget,
    calculate_score,
    load_recommender_config,
    quiz_cache_key,
    recommend,
)

TOTAL = dict(budget_min_toman=60_000_000, budget_max_toman=150_000_000)


def _quiz(**overrides) -> dict:
    quiz = {
        "styles": ["modern"],
        "color_palette": ["#2E2E2E", "#FFFFFF"],
        "room_width_cm": 400,
        "room_length_cm": 500,
        "materials": ["wood"],
        "patterns": ["solid"],
        **TOTAL,
    }
    quiz.update(overrides)
    return quiz


def _product(title: str, category: str, price: int, **kw) -> Product:
    from ai.embedding_service import get_embedding

    return Product(
        id=uuid.uuid4().hex, title=title, category=category, room_type="living_room",
        price_toman=price, image_url="https://images.example.com/x.jpg",
        seller_link="https://seller.example.com/p/1", is_verified=True, integrity_ok=True,
        styles=kw.get("styles", ["modern"]), colors=kw.get("colors", ["#2E2E2E"]),
        materials=kw.get("materials", ["fabric"]), patterns=kw.get("patterns", ["solid"]),
        width_cm=kw.get("width", 0), depth_cm=kw.get("depth", 0), height_cm=kw.get("height", 0),
        style_embedding=get_embedding(f"{title} modern"),
    )


def _tmp_config(tmp_path, mutate) -> str:
    cfg = json.loads(json.dumps(rec.CONFIG))
    mutate(cfg)
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return p


# ------------------------------------------------------------------ 1. math
class TestAllocateBudget:
    def test_full_set_uses_the_configured_shares(self):
        alloc = allocate_budget(60_000_000, 150_000_000, list(CATEGORIES))
        assert set(alloc) == set(CATEGORIES)
        for c in CATEGORIES:
            assert alloc[c]["min"] == int(60_000_000 * BUDGET_SHARES[c]["min"])
            assert alloc[c]["max"] == pytest.approx(150_000_000 * BUDGET_SHARES[c]["max"], abs=1)

    def test_min_shares_are_a_complete_basket(self):
        """Σ min == 1: a user who spends exactly the floor buys one of each."""
        alloc = allocate_budget(60_000_000, 150_000_000, list(CATEGORIES))
        assert sum(w["min"] for w in alloc.values()) == pytest.approx(60_000_000, abs=len(CATEGORIES))
        assert abs(sum(s["min"] for s in BUDGET_SHARES.values()) - 1.0) < 1e-6

    def test_no_single_category_may_exceed_the_total(self):
        alloc = allocate_budget(60_000_000, 150_000_000, list(CATEGORIES))
        assert all(w["max"] <= 150_000_000 for w in alloc.values())
        assert max(w["max"] for w in alloc.values()) == alloc["sofa"]["max"]

    def test_single_category_gets_the_whole_window(self):
        """``categories=["sofa"]`` with 44–46M means sofas between 44M and 46M —
        the contract every pre-ADR-019 single-category test relied on."""
        for c in CATEGORIES:
            assert allocate_budget(44_000_000, 46_000_000, [c]) == {c: {"min": 44_000_000, "max": 46_000_000}}

    def test_subset_renormalises_and_stays_within_the_total(self):
        alloc = allocate_budget(40_000_000, 100_000_000, ["sofa", "rug"])
        assert alloc["sofa"]["min"] + alloc["rug"]["min"] == pytest.approx(40_000_000, abs=2)
        assert alloc["sofa"]["min"] > alloc["rug"]["min"]
        assert alloc["sofa"]["max"] <= 100_000_000 and alloc["rug"]["max"] <= 100_000_000
        # The bigger share of the two takes the whole ceiling.
        assert alloc["sofa"]["max"] == 100_000_000

    def test_per_item_mode_is_the_legacy_single_window(self):
        alloc = allocate_budget(1_000_000, 20_000_000, list(CATEGORIES), "per_item")
        assert all(w == {"min": 1_000_000, "max": 20_000_000} for w in alloc.values())

    def test_unknown_mode_is_refused(self):
        with pytest.raises(ValueError, match="budget_mode"):
            allocate_budget(1, 2, ["sofa"], "guess")

    def test_unknown_category_degrades_to_the_total_window(self):
        alloc = allocate_budget(5_000_000, 50_000_000, ["sofa", "hammock"])
        assert alloc["hammock"] == {"min": 5_000_000, "max": 50_000_000}
        assert alloc["sofa"]["max"] == 50_000_000  # only known category → whole ceiling

    def test_windows_are_integers_and_ordered(self):
        for lo, hi in [(0, 1), (1, 1), (3, 7), (999_999, 1_000_001), (0, 2_000_000_000)]:
            for w in allocate_budget(lo, hi, list(CATEGORIES)).values():
                assert isinstance(w["min"], int) and isinstance(w["max"], int)
                assert 0 <= w["min"] <= w["max"] <= max(lo, hi)

    def test_monotone_in_the_total(self):
        a = allocate_budget(10_000_000, 50_000_000, list(CATEGORIES))
        b = allocate_budget(20_000_000, 100_000_000, list(CATEGORIES))
        for c in CATEGORIES:
            assert b[c]["min"] >= a[c]["min"] and b[c]["max"] >= a[c]["max"]

    def test_inverted_input_is_normalised_not_crashed(self):
        alloc = allocate_budget(50_000_000, 10_000_000, ["sofa"])
        assert alloc["sofa"] == {"min": 50_000_000, "max": 50_000_000}


# ----------------------------------------------------- 2. config validation
class TestBudgetConfigValidation:
    def test_section_present_and_well_formed(self):
        section = rec.CONFIG["budget"]
        assert section["mode"] in BUDGET_MODES
        assert set(section["category_share"]) == set(CATEGORIES)
        assert rec.DEFAULT_BUDGET_MODE == "split_total"

    def test_missing_section_is_rejected(self, tmp_path):
        def mutate(cfg):
            del cfg["budget"]
        with pytest.raises(RuntimeError, match="budget section missing"):
            load_recommender_config(_tmp_config(tmp_path, mutate))

    def test_unknown_mode_is_rejected(self, tmp_path):
        def mutate(cfg):
            cfg["budget"]["mode"] = "guess"
        with pytest.raises(RuntimeError, match="budget.mode 'guess'"):
            load_recommender_config(_tmp_config(tmp_path, mutate))

    def test_missing_category_is_rejected(self, tmp_path):
        def mutate(cfg):
            del cfg["budget"]["category_share"]["decor"]
        with pytest.raises(RuntimeError, match="category_share keys"):
            load_recommender_config(_tmp_config(tmp_path, mutate))

    def test_min_shares_must_sum_to_one(self, tmp_path):
        def mutate(cfg):
            cfg["budget"]["category_share"]["sofa"]["min"] = 0.5
        with pytest.raises(RuntimeError, match="min shares sum to"):
            load_recommender_config(_tmp_config(tmp_path, mutate))

    def test_max_shares_must_cover_the_total(self, tmp_path):
        def mutate(cfg):
            for share in cfg["budget"]["category_share"].values():
                share["max"] = share["min"] = round(share["min"], 6)
            # Σmin == 1 still holds; Σmax == 1 is fine; push one below its min.
            cfg["budget"]["category_share"]["sofa"]["max"] = 0.39
        with pytest.raises(RuntimeError, match="0 < min <= max <= 1"):
            load_recommender_config(_tmp_config(tmp_path, mutate))

    def test_max_sum_below_one_is_rejected(self, tmp_path):
        def mutate(cfg):
            shares = cfg["budget"]["category_share"]
            for c, share in shares.items():
                share["max"] = share["min"] / 2 if c != "sofa" else share["min"]
                share["min"] = share["max"]
            # Σmin is now < 1 as well; the validator reports both, we match one.
        with pytest.raises(RuntimeError, match="max shares sum to"):
            load_recommender_config(_tmp_config(tmp_path, mutate))


# ------------------------------------------------------------- 3. the engine
class TestEngine:
    def test_cheap_real_rows_are_recommendable_for_a_normal_total(self, db):
        """A 900k cushion and a 3M lamp — the price points the seller-feed
        importer actually brings in — must be candidates for a 10–100M room
        total (the questionnaire's default window). Under the old single
        window (10M floor) both were invisible."""
        cushion = _product("Linen Cushion 45x45", "decor", 900_000, materials=["fabric"])
        lamp = _product("Brass Floor Lamp 150", "lighting", 3_000_000, materials=["metal"])
        db.add_all([cushion, lamp])
        db.commit()
        try:
            res = recommend(db, _quiz(budget_min_toman=10_000_000, budget_max_toman=100_000_000),
                            use_cache=False)
            alloc = res["meta"]["budget_allocation"]
            assert alloc["decor"]["min"] > 0  # the floor is scaled, not dropped
            assert alloc["decor"]["min"] <= 900_000 <= alloc["decor"]["max"]
            assert alloc["lighting"]["min"] <= 3_000_000 <= alloc["lighting"]["max"]
            pool_decor = rec._stage_a_hard_filter(db, "decor", alloc["decor"]["min"], alloc["decor"]["max"])
            pool_light = rec._stage_a_hard_filter(db, "lighting", alloc["lighting"]["min"], alloc["lighting"]["max"])
            assert cushion.id in {p.id for p in pool_decor}
            assert lamp.id in {p.id for p in pool_light}
        finally:
            db.delete(cushion)
            db.delete(lamp)
            db.commit()

    def test_a_rug_that_eats_the_whole_total_is_not_recommended(self, db):
        """20M in total for the room can never mean a 19M rug: with the sofa
        share alone at 40 % of the floor, the rug window tops out far below."""
        rug = _product("Hand-knotted Wool Rug 3x2", "rug", 19_000_000, materials=["fabric"])
        db.add(rug)
        db.commit()
        try:
            res = recommend(db, _quiz(budget_min_toman=5_000_000, budget_max_toman=20_000_000),
                            use_cache=False)
            alloc = res["meta"]["budget_allocation"]
            assert alloc["rug"]["max"] < 19_000_000
            assert rug.id not in {i["id"] for i in res["categories"].get("rug", [])}
            # ...while the legacy mode would have accepted it.
            legacy = recommend(db, _quiz(budget_min_toman=5_000_000, budget_max_toman=20_000_000,
                                         budget_mode="per_item"), categories=["rug"], use_cache=False)
            assert legacy["meta"]["budget_allocation"]["rug"] == {"min": 5_000_000, "max": 20_000_000}
        finally:
            db.delete(rug)
            db.commit()

    def test_every_returned_price_sits_inside_its_category_window(self, db):
        res = recommend(db, _quiz(), use_cache=False)
        alloc = res["meta"]["budget_allocation"]
        assert res["categories"], "seeded catalog returned nothing"
        for category, items in res["categories"].items():
            for item in items:
                assert alloc[category]["min"] <= item["price_toman"] <= alloc[category]["max"]

    def test_budget_fit_is_scored_against_the_category_window(self, db):
        """A sofa priced at the midpoint of the SOFA window scores 100 % on
        budget_fit even though it is nowhere near the midpoint of the total."""
        alloc = allocate_budget(TOTAL["budget_min_toman"], TOTAL["budget_max_toman"], list(CATEGORIES))
        mid = (alloc["sofa"]["min"] + alloc["sofa"]["max"]) // 2
        sofa = _product("Midpoint Sofa", "sofa", mid)
        score = calculate_score(sofa, _quiz(), style_sim=0.5)
        assert score["explanation"]["budget_fit"] == 100
        # The same price judged against the TOTAL window would not be 100.
        total_mid = (TOTAL["budget_min_toman"] + TOTAL["budget_max_toman"]) / 2
        assert abs(mid - total_mid) > 1_000_000

    def test_meta_echoes_mode_total_and_allocation(self, db):
        res = recommend(db, _quiz(), categories=["sofa", "rug"], use_cache=False)
        meta = res["meta"]
        assert meta["budget_min_toman"] == TOTAL["budget_min_toman"]
        assert meta["budget_max_toman"] == TOTAL["budget_max_toman"]
        assert meta["budget_mode"] == "split_total"
        assert set(meta["budget_allocation"]) == {"sofa", "rug"}
        assert meta["budget_allocation"] == allocate_budget(
            TOTAL["budget_min_toman"], TOTAL["budget_max_toman"], ["sofa", "rug"])

    def test_explanation_still_reconstructs_the_final_score(self, db):
        res = recommend(db, _quiz(), use_cache=False)
        w = res["meta"]["weights"]
        checked = 0
        for items in res["categories"].values():
            for item in items:
                e = item["explanation"]
                recomputed = sum(
                    w[k] * e[f] / 100 for k, f in (
                        ("style", "style_match"), ("color", "color_match"), ("budget", "budget_fit"),
                        ("material", "material_match"), ("pattern", "pattern_match"), ("fit", "fit_match"),
                    )
                )
                assert item["final_score"] == pytest.approx(recomputed, abs=0.021)
                checked += 1
        assert checked >= 5

    def test_private_window_key_never_leaks(self, db):
        res = recommend(db, _quiz(), use_cache=False)
        for items in res["categories"].values():
            for item in items:
                assert "_budget_windows" not in item
        assert "_budget_windows" not in res["meta"]


# ------------------------------------------------------------- 4. the cache
class TestCacheIdentity:
    def test_mode_is_part_of_the_key_even_when_defaulted(self):
        base = {**_quiz(), "_categories": list(CATEGORIES), "_fb": None,
                "_profile": "current", "_cfg": rec.CONFIG["config_version"]}
        a = quiz_cache_key({**base, "_budget_mode": "split_total"}, "u1")
        b = quiz_cache_key({**base, "_budget_mode": "per_item"}, "u1")
        assert a != b

    def test_cached_payload_is_served_per_mode(self, db):
        first = recommend(db, _quiz(), categories=["sofa"], user_id="u-adr019")
        legacy = recommend(db, _quiz(budget_mode="per_item"), categories=["sofa"], user_id="u-adr019")
        again = recommend(db, _quiz(), categories=["sofa"], user_id="u-adr019")
        assert first["cached"] is False
        assert legacy["cached"] is False and legacy["meta"]["budget_mode"] == "per_item"
        assert again["cached"] is True and again["meta"]["budget_mode"] == "split_total"


# ---------------------------------------------------------------- 5. HTTP
class TestHttp:
    def test_recommend_accepts_optional_mode_and_returns_allocation(self, client, auth_headers):
        headers, _ = auth_headers
        body = {k: v for k, v in _quiz().items()}
        r = client.post("/api/v1/recommend", json=body, headers=headers)
        assert r.status_code == 200, r.text
        meta = r.json()["data"]["meta"]
        assert meta["budget_mode"] == "split_total"
        assert set(meta["budget_allocation"]) == set(CATEGORIES)

        r = client.post("/api/v1/recommend", json={**body, "budget_mode": "per_item"}, headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["meta"]["budget_mode"] == "per_item"

    def test_unknown_mode_is_a_422(self, client, auth_headers):
        headers, _ = auth_headers
        r = client.post("/api/v1/recommend", json={**_quiz(), "budget_mode": "guess"}, headers=headers)
        assert r.status_code == 422

    def test_saved_quiz_path_uses_the_default_mode(self, client, auth_headers):
        headers, _ = auth_headers
        created = client.post("/api/v1/quiz", json=_quiz(), headers=headers)
        assert created.status_code in (200, 201), created.text
        quiz_id = created.json()["data"]["id"]
        r = client.post(f"/api/v1/recommend?quiz_id={quiz_id}", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["meta"]["budget_mode"] == "split_total"
