"""ADR-012 — dimensional fit as the sixth explainable ranking component.

The quiz has always carried ``room_width_cm`` / ``room_length_cm`` and every
catalog row carries ``width_cm`` / ``depth_cm`` / ``height_cm``; until
2026-09-06 the ranking ignored both. These tests pin the behaviour of
``fit_score`` (pure function) and its integration into ``calculate_score`` /
``recommend`` (breakdown fidelity, cache identity, ordering effect).
"""
from __future__ import annotations

import uuid

import pytest

from app.models.product import Product
from app.services import recommender as rec
from app.services.recommender import (
    FIT_CONFIG,
    WEIGHTS,
    calculate_score,
    fit_score,
    quiz_cache_key,
    recommend,
)

ROOM = dict(room_width_cm=400, room_length_cm=500)  # 20 m² living room
SMALL_ROOM = dict(room_width_cm=250, room_length_cm=300)  # 7.5 m² studio


def _quiz(**overrides) -> dict:
    quiz = {
        "styles": ["modern"],
        "color_palette": ["#2E2E2E", "#FFFFFF"],
        "budget_min_toman": 1_000_000,
        "budget_max_toman": 150_000_000,
        "materials": ["wood"],
        "patterns": ["solid"],
        **ROOM,
    }
    quiz.update(overrides)
    return quiz


def _product(title: str, **kw) -> Product:
    from ai.embedding_service import get_embedding

    d = dict(category="sofa", price=50_000_000, styles=["modern"], materials=["wood"],
             colors=["#2E2E2E"], patterns=["solid"], width=220, depth=95, height=85)
    d.update(kw)
    return Product(
        id=uuid.uuid4().hex, title=title, category=d["category"], room_type="living_room",
        price_toman=d["price"], image_url="https://images.example.com/x.jpg", is_verified=True,
        styles=d["styles"], colors=d["colors"], materials=d["materials"], patterns=d["patterns"],
        width_cm=d["width"], depth_cm=d["depth"], height_cm=d["height"],
        style_embedding=get_embedding(f"{title} {d['styles'][0]}"),
    )


# ---------------------------------------------------------------------------
# Pure function
# ---------------------------------------------------------------------------
class TestFitScoreFunction:
    def test_config_is_versioned_with_the_weights(self):
        assert "fit" in WEIGHTS and WEIGHTS["fit"] > 0
        assert set(FIT_CONFIG["categories"]) == {
            "sofa", "coffee_table", "chair", "storage", "rug", "decor", "lighting"
        }
        assert 0 < FIT_CONFIG["floor"] < FIT_CONFIG["neutral_score"] < 1

    @pytest.mark.parametrize("category", ["sofa", "coffee_table", "chair", "storage", "rug"])
    def test_unknown_dimensions_are_neutral_not_penalised(self, category):
        assert fit_score(category, None, None, None, 400, 500) == (0.5, "fit_unknown")
        assert fit_score(category, 0, 0, 0, 400, 500) == (0.5, "fit_unknown")
        assert fit_score(category, 200, 90, 80, None, None) == (0.5, "fit_unknown")

    def test_lighting_is_footprint_neutral(self):
        assert fit_score("lighting", 28, 39, 57, 400, 500) == (0.5, "fit_neutral")

    def test_unknown_category_is_neutral(self):
        assert fit_score("sauna", 200, 200, 200, 400, 500) == (0.5, "fit_neutral")

    def test_scores_are_bounded(self):
        for cat in FIT_CONFIG["categories"]:
            for w, d, h in [(1, 1, 1), (50, 50, 50), (200, 90, 85), (400, 300, 300), (900, 900, 900)]:
                for rw, rl in [(100, 100), (250, 300), (400, 500), (3000, 3000)]:
                    score, reason = fit_score(cat, w, d, h, rw, rl)
                    assert 0.0 <= score <= 1.0, (cat, w, d, rw, rl)
                    assert reason.startswith("fit_")

    # --- seating / tables / storage: too big is the failure mode ---------
    def test_sofa_that_fits_comfortably_scores_full(self):
        assert fit_score("sofa", 220, 95, 85, **ROOM) == (1.0, "fit_ok")

    def test_sofa_longer_than_the_room_is_floored(self):
        score, reason = fit_score("sofa", 320, 100, 85, **SMALL_ROOM)
        assert score == FIT_CONFIG["floor"] and reason == "fit_too_big"

    def test_sofa_that_blocks_circulation_is_floored(self):
        # 250 cm short wall - 200 cm sofa leaves 50 cm < 76 cm lane, and the
        # sofa cannot be turned (90 cm depth leaves 160 cm, fine) -> the rule
        # only fires when BOTH orientations fail, so this one must survive...
        score, _ = fit_score("sofa", 200, 90, 85, **SMALL_ROOM)
        assert score > FIT_CONFIG["floor"]
        # ...whereas a 200 x 190 cm sectional cannot leave a lane either way.
        score, reason = fit_score("sofa", 200, 190, 85, **SMALL_ROOM)
        assert score == FIT_CONFIG["floor"] and reason == "fit_too_big"

    def test_sofa_fit_is_monotone_in_room_size(self):
        scores = [fit_score("sofa", 244, 104, 70, w, int(w * 1.2))[0] for w in range(250, 600, 25)]
        assert scores == sorted(scores), scores
        assert scores[0] < 0.6 < scores[-1] == 1.0

    def test_coffee_table_and_chair_use_their_own_ratios(self):
        assert fit_score("coffee_table", 139, 79, 45, **ROOM)[0] > 0.8
        assert fit_score("coffee_table", 139, 79, 45, 200, 250) == (FIT_CONFIG["floor"], "fit_too_big")
        assert fit_score("chair", 95, 95, 96, **ROOM)[0] > 0.9

    # --- rugs: too small is the failure mode -----------------------------
    def test_rug_too_small_for_the_room_is_penalised(self):
        big_room = dict(room_width_cm=800, room_length_cm=900)
        score, reason = fit_score("rug", 240, 198, 1, **big_room)
        assert reason == "fit_too_small" and score < 0.5

    def test_rug_at_ideal_coverage_scores_high(self):
        # 250 x 159 in 300 x 350 -> ~38% coverage, right at the ideal 40%
        score, reason = fit_score("rug", 250, 159, 2, 300, 350)
        assert reason == "fit_ok" and score > 0.9

    def test_rug_larger_than_the_room_is_floored(self):
        assert fit_score("rug", 336, 238, 1, 300, 230) == (FIT_CONFIG["floor"], "fit_too_big")

    # --- decor: height against the assumed ceiling -----------------------
    def test_curtain_at_ceiling_height_scores_full(self):
        assert fit_score("decor", 251, 1, 273, **ROOM) == (1.0, "fit_ok")

    def test_short_curtain_is_penalised_not_floored(self):
        score, reason = fit_score("decor", 251, 1, 180, **ROOM)
        assert reason == "fit_too_small" and FIT_CONFIG["floor"] < score < 1.0

    def test_decor_taller_than_any_ceiling_is_floored(self):
        assert fit_score("decor", 100, 1, 320, **ROOM) == (FIT_CONFIG["floor"], "fit_too_tall")


# ---------------------------------------------------------------------------
# Integration with calculate_score / recommend
# ---------------------------------------------------------------------------
class TestFitInsideTheEngine:
    def test_breakdown_carries_fit_and_reconstructs_final(self):
        p = _product("Compact Modern Sofa", width=180, depth=85)
        score = calculate_score(p, _quiz(), style_sim=0.8)
        exp = score["explanation"]
        assert exp["fit_match"] == 100 and exp["fit_reason"] == "fit_ok"
        reconstructed = (
            WEIGHTS["style"] * 0.8
            + WEIGHTS["color"] * exp["color_match"] / 100
            + WEIGHTS["budget"] * exp["budget_fit"] / 100
            + WEIGHTS["material"] * exp["material_match"] / 100
            + WEIGHTS["pattern"] * exp["pattern_match"] / 100
            + WEIGHTS["fit"] * exp["fit_match"] / 100
        )
        assert score["final_score"] == pytest.approx(reconstructed, abs=0.02)

    def test_quiz_without_room_dimensions_is_neutral(self):
        """Older saved quizzes / inline payloads without room dims keep working."""
        p = _product("Any Sofa")
        q = _quiz()
        q.pop("room_width_cm")
        q.pop("room_length_cm")
        exp = calculate_score(p, q, style_sim=0.8)["explanation"]
        assert exp["fit_match"] == 50 and exp["fit_reason"] == "fit_unknown"

    def test_v1_profile_ranks_exactly_as_before_fit_existed(self):
        """`current-v1` pins fit at 0 so it is a faithful pre-ADR-012 baseline."""
        p = _product("Oversized Sofa", width=300, depth=120)
        v1 = rec.get_weights("current-v1")
        score = calculate_score(p, _quiz(**SMALL_ROOM), style_sim=0.8, weights=v1)
        exp = score["explanation"]
        assert exp["fit_reason"] == "fit_too_big"  # still explained...
        expected = (0.30 * 0.8 + 0.30 * exp["color_match"] / 100 + 0.20 * exp["budget_fit"] / 100
                    + 0.15 * exp["material_match"] / 100 + 0.05 * exp["pattern_match"] / 100)
        assert score["final_score"] == pytest.approx(expected, abs=0.02)  # ...but not scored

    def test_oversized_sofa_drops_below_a_fitting_twin_in_a_small_room(self, db):
        # Identical taste signals; the only difference is the footprint. A
        # narrow budget window isolates the pair from the seeded catalog so
        # both survive the MAX_RESULTS cut and can be compared directly.
        band = dict(budget_min_toman=123_000_000, budget_max_toman=124_000_000)
        fits = _product("Studio Sofa Compact", width=170, depth=85, price=123_400_000)
        huge = _product("Studio Sofa Grand", width=240, depth=180, price=123_600_000)
        db.add_all([fits, huge])
        db.commit()

        res = recommend(db, _quiz(**SMALL_ROOM, **band), categories=["sofa"], use_cache=False)
        sofas = res["categories"]["sofa"]
        ids = [s["id"] for s in sofas]
        assert ids.index(fits.id) < ids.index(huge.id)
        by_id = {s["id"]: s for s in sofas}
        assert by_id[huge.id]["explanation"]["fit_reason"] == "fit_too_big"
        assert by_id[fits.id]["explanation"]["fit_match"] > by_id[huge.id]["explanation"]["fit_match"]

        # In a large room the same pair is no longer separated by fit.
        res_big = recommend(db, _quiz(room_width_cm=700, room_length_cm=800, **band),
                            categories=["sofa"], use_cache=False)
        by_id_big = {s["id"]: s for s in res_big["categories"]["sofa"]}
        assert by_id_big[huge.id]["explanation"]["fit_reason"] in ("fit_ok", "fit_tight")

    def test_room_dimensions_and_config_version_are_part_of_the_cache_identity(self):
        a = quiz_cache_key({**_quiz(), "_cfg": rec.CONFIG["config_version"]}, "u1")
        b = quiz_cache_key({**_quiz(room_width_cm=250), "_cfg": rec.CONFIG["config_version"]}, "u1")
        c = quiz_cache_key({**_quiz(), "_cfg": "0000-00-00.0"}, "u1")
        assert len({a, b, c}) == 3

    def test_meta_reports_the_bumped_config_and_fit_weight(self, db):
        res = recommend(db, _quiz(), use_cache=False)
        assert res["meta"]["weights_version"] == "2026-09-06.1"
        assert res["meta"]["weights"]["fit"] == WEIGHTS["fit"]
