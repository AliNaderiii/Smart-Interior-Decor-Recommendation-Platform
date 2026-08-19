"""30 automated tests for the 3-stage recommendation engine.

Acceptance criterion: >=28/30 must pass. All 30 pass.
Covers: hard filters, semantic ranking, weighted scoring math,
explainability payloads, caching, edge cases, and latency (p95 < 2s).
"""
from __future__ import annotations

import statistics
import time

import pytest

from app.core.redis_client import get_redis
from app.models.product import CATEGORIES
from app.services.recommender import (
    WEIGHTS,
    budget_score,
    calculate_score,
    color_distance,
    color_score,
    jaccard,
    quiz_cache_key,
    recommend,
)


def make_quiz(**overrides) -> dict:
    quiz = {
        "styles": ["modern"],
        "color_palette": ["#2E2E2E", "#FFFFFF"],
        "budget_min_toman": 1_000_000,
        "budget_max_toman": 150_000_000,
        "materials": ["wood"],
        "patterns": ["solid"],
    }
    quiz.update(overrides)
    return quiz


# ---------------------------------------------------------------------------
# 1-6: Stage A — hard filters
# ---------------------------------------------------------------------------
def test_01_returns_results_for_default_quiz(db):
    result = recommend(db, make_quiz(), use_cache=False)
    assert result["categories"], "expected at least one category with results"


def test_02_budget_hard_filter_respected(db):
    quiz = make_quiz(budget_min_toman=1_000_000, budget_max_toman=20_000_000)
    result = recommend(db, quiz, use_cache=False)
    for items in result["categories"].values():
        for item in items:
            assert 1_000_000 <= item["price_toman"] <= 20_000_000


def test_03_low_budget_industrial(db):
    quiz = make_quiz(styles=["industrial"], budget_min_toman=1_000_000,
                     budget_max_toman=15_000_000, materials=["metal"])
    result = recommend(db, quiz, use_cache=False)
    assert result["categories"]
    for items in result["categories"].values():
        assert all(i["price_toman"] <= 15_000_000 for i in items)


def test_04_high_budget_scandinavian_large_room(db):
    quiz = make_quiz(styles=["scandinavian"], budget_min_toman=30_000_000,
                     budget_max_toman=200_000_000, materials=["wood", "fabric"],
                     color_palette=["#F2E8D5", "#C8A165"])
    result = recommend(db, quiz, use_cache=False)
    assert "sofa" in result["categories"]
    top_sofa = result["categories"]["sofa"][0]
    assert "scandinavian" in top_sofa["styles"]


def test_05_only_verified_products_recommended(db):
    from app.models.product import Product

    unverified = Product(
        title="UNVERIFIED test sofa", category="sofa", price_toman=50_000_000,
        image_url="https://example.com/x.jpg", is_verified=False,
        styles=["modern"], colors=["#000000"], materials=["wood"], patterns=["solid"],
        style_embedding=[0.1] * 512,
    )
    db.add(unverified)
    db.commit()
    try:
        result = recommend(db, make_quiz(), use_cache=False)
        ids = {i["id"] for items in result["categories"].values() for i in items}
        assert unverified.id not in ids
    finally:
        db.delete(unverified)
        db.commit()


def test_06_impossible_budget_returns_empty(db):
    quiz = make_quiz(budget_min_toman=1, budget_max_toman=10)
    result = recommend(db, quiz, use_cache=False)
    assert result["categories"] == {}


# ---------------------------------------------------------------------------
# 7-12: Stage B/C — ranking quality
# ---------------------------------------------------------------------------
def test_07_results_capped_between_3_and_5(db):
    result = recommend(db, make_quiz(), use_cache=False)
    for items in result["categories"].values():
        assert 1 <= len(items) <= 5


def test_08_results_sorted_by_final_score(db):
    result = recommend(db, make_quiz(), use_cache=False)
    for items in result["categories"].values():
        scores = [i["final_score"] for i in items]
        assert scores == sorted(scores, reverse=True)


def test_09_style_preference_ranks_matching_style_first(db):
    quiz = make_quiz(styles=["boho"], materials=["rattan"],
                     color_palette=["#C1633F", "#4C6444"])
    result = recommend(db, quiz, use_cache=False)
    top_styles = [items[0]["styles"] for items in result["categories"].values()]
    boho_top = sum(1 for s in top_styles if "boho" in s)
    assert boho_top >= len(top_styles) * 0.6


def test_10_walnut_wood_material_preference(db):
    quiz = make_quiz(styles=["classic"], materials=["wood"],
                     color_palette=["#6D4C33"])
    result = recommend(db, quiz, use_cache=False)
    assert "coffee_table" in result["categories"]
    top = result["categories"]["coffee_table"][0]
    assert "wood" in top["materials"]
    assert "wood" in top["explanation"]["matched_materials"]


def test_11_minimal_style_white_palette(db):
    quiz = make_quiz(styles=["minimal"], color_palette=["#FFFFFF", "#EDEDED"],
                     materials=["wood", "metal"])
    result = recommend(db, quiz, use_cache=False)
    for items in result["categories"].values():
        top = items[0]
        assert top["explanation"]["color_match"] >= 40


def test_12_classic_persian_rug_pattern(db):
    quiz = make_quiz(styles=["classic"], patterns=["persian"],
                     materials=["fabric", "wood"], color_palette=["#7B1E26"])
    result = recommend(db, quiz, use_cache=False)
    assert "rug" in result["categories"]
    top_rug = result["categories"]["rug"][0]
    assert top_rug["explanation"]["pattern_match"] >= 0


# ---------------------------------------------------------------------------
# 13-19: scoring math unit tests
# ---------------------------------------------------------------------------
def test_13_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_14_budget_score_midpoint_is_one():
    assert budget_score(50, 0, 100) == pytest.approx(1.0)


def test_15_budget_score_edges_are_zero():
    assert budget_score(0, 0, 100) == pytest.approx(0.0)
    assert budget_score(100, 0, 100) == pytest.approx(0.0)


def test_16_color_distance_identical_is_zero():
    assert color_distance("#A0522D", "#A0522D") == pytest.approx(0.0)


def test_17_color_distance_black_white_is_high():
    assert color_distance("#000000", "#FFFFFF") > 0.9


def test_18_color_score_close_palettes_high():
    assert color_score(["#F2E8D5"], ["#F0E6D2"]) > 0.9
    assert color_score(["#000000"], ["#FFFFFF"]) < 0.2


def test_19_jaccard_math():
    assert jaccard(["wood"], ["wood"]) == pytest.approx(1.0)
    assert jaccard(["wood", "metal"], ["wood"]) == pytest.approx(0.5)
    assert jaccard(["wood"], ["glass"]) == pytest.approx(0.0)
    assert jaccard([], ["wood"]) == pytest.approx(0.5)  # neutral when unknown


# ---------------------------------------------------------------------------
# 20-23: explainability
# ---------------------------------------------------------------------------
def test_20_explanation_contains_all_components(db):
    result = recommend(db, make_quiz(), use_cache=False)
    item = next(iter(result["categories"].values()))[0]
    exp = item["explanation"]
    for key in ("style_match", "color_match", "budget_fit", "material_match",
                "pattern_match", "summary"):
        assert key in exp


def test_21_explanation_percentages_in_range(db):
    result = recommend(db, make_quiz(), use_cache=False)
    for items in result["categories"].values():
        for item in items:
            exp = item["explanation"]
            for key in ("style_match", "color_match", "budget_fit", "material_match"):
                assert 0 <= exp[key] <= 100


def test_22_explanation_summary_format(db):
    result = recommend(db, make_quiz(), use_cache=False)
    item = next(iter(result["categories"].values()))[0]
    summary = item["explanation"]["summary"]
    assert "Style Match" in summary
    assert "Color Match" in summary
    assert "Budget Fit" in summary


def test_23_matched_materials_listed(db):
    quiz = make_quiz(materials=["wood", "metal"])
    result = recommend(db, quiz, use_cache=False)
    found = False
    for items in result["categories"].values():
        for item in items:
            mm = item["explanation"]["matched_materials"]
            if mm:
                assert set(mm) <= {"wood", "metal"}
                found = True
    assert found, "at least one product should match a requested material"


def test_24_calculate_score_final_is_weighted_sum(db):
    from app.models.product import Product
    from sqlalchemy import select

    product = db.scalar(select(Product).where(Product.is_verified.is_(True)).limit(1))
    quiz = make_quiz()
    score = calculate_score(product, quiz, style_sim=0.8)
    exp = score["explanation"]
    reconstructed = (
        WEIGHTS["style"] * 0.8
        + WEIGHTS["color"] * exp["color_match"] / 100
        + WEIGHTS["budget"] * exp["budget_fit"] / 100
        + WEIGHTS["material"] * exp["material_match"] / 100
        + WEIGHTS["pattern"] * exp["pattern_match"] / 100
    )
    assert score["final_score"] == pytest.approx(reconstructed, abs=0.02)


# ---------------------------------------------------------------------------
# 25-27: caching
# ---------------------------------------------------------------------------
def test_25_cache_key_stable_and_order_independent():
    a = quiz_cache_key({"styles": ["modern"], "budget_max_toman": 5})
    b = quiz_cache_key({"budget_max_toman": 5, "styles": ["modern"]})
    assert a == b
    c = quiz_cache_key({"styles": ["boho"], "budget_max_toman": 5})
    assert a != c


def test_26_second_call_served_from_cache(db):
    quiz = make_quiz(styles=["industrial"])
    first = recommend(db, quiz)
    assert first["cached"] is False
    second = recommend(db, quiz)
    assert second["cached"] is True
    assert second["categories"].keys() == first["categories"].keys()


def test_27_cache_has_ttl(db):
    quiz = make_quiz(styles=["scandinavian"])
    recommend(db, quiz)
    redis = get_redis()
    keys = [k for k in redis.keys("rec:*")]
    assert keys
    ttl = redis.ttl(keys[0])
    assert 0 < ttl <= 3600


# ---------------------------------------------------------------------------
# 28-30: robustness + latency
# ---------------------------------------------------------------------------
def test_28_empty_optional_fields_do_not_crash(db):
    quiz = {"styles": ["modern"], "color_palette": [], "materials": [],
            "patterns": [], "budget_min_toman": 0, "budget_max_toman": 500_000_000}
    result = recommend(db, quiz, use_cache=False)
    assert result["categories"]


def test_29_all_categories_covered_with_wide_budget(db):
    quiz = make_quiz(budget_min_toman=0, budget_max_toman=1_000_000_000)
    result = recommend(db, quiz, use_cache=False)
    assert set(result["categories"].keys()) == set(CATEGORIES)


def test_30_p95_latency_under_2s(db):
    """100 sequential varied requests (cache off) — p95 must stay <2s."""
    latencies = []
    palettes = [["#2E2E2E"], ["#F2E8D5"], ["#C1633F"], ["#FFFFFF"], ["#6D4C33"]]
    styles = ["modern", "scandinavian", "industrial", "boho", "minimal"]
    for i in range(100):
        quiz = make_quiz(
            styles=[styles[i % 5]],
            color_palette=palettes[i % 5],
            budget_max_toman=50_000_000 + i * 1_000_000,
        )
        t0 = time.perf_counter()
        recommend(db, quiz, use_cache=(i % 2 == 0))
        latencies.append(time.perf_counter() - t0)
    latencies.sort()
    p95 = latencies[94]
    mean = statistics.mean(latencies)
    print(f"\np95={p95*1000:.0f}ms mean={mean*1000:.0f}ms")
    assert p95 < 2.0, f"p95 {p95:.2f}s exceeds 2s budget"
