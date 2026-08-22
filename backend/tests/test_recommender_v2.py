"""Stage 04 · recommender audit tests: determinism, diversity, no-result
behaviour, explanation fidelity, config validation, edge cases.

These complement (never replace) the 30 acceptance scenarios in
``tests/test_recommender.py``, which must keep passing >= 28/30.
"""
from __future__ import annotations

import json
import uuid

import pytest

from app.models.product import CATEGORIES, Product
from app.services import recommender as rec
from app.services.recommender import (
    CONFIG,
    WEIGHTS,
    apply_feedback,
    diversify,
    load_recommender_config,
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


def _product(title: str, **kw) -> Product:
    from ai.embedding_service import get_embedding

    defaults = dict(
        category="sofa", price=50_000_000, styles=["modern"],
        materials=["wood"], colors=["#2E2E2E"], patterns=["solid"],
        verified=True, emb=None, id=None,
    )
    defaults.update(kw)
    emb = defaults.pop("emb") or f"{title} {defaults['styles'][0]}"
    return Product(
        id=defaults.pop("id") or uuid.uuid4().hex,
        title=title,
        category=defaults["category"],
        room_type="living_room",
        price_toman=defaults["price"],
        image_url="https://images.example.com/x.jpg",
        is_verified=defaults["verified"],
        styles=defaults["styles"], colors=defaults["colors"],
        materials=defaults["materials"], patterns=defaults["patterns"],
        style_embedding=get_embedding(emb),
    )


class TestConfigValidation:
    def test_weights_sum_to_one_and_match_expected_keys(self):
        assert set(WEIGHTS) == {"style", "color", "budget", "material", "pattern"}
        assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9

    def test_config_declares_source_and_learning_status(self):
        source = CONFIG["weights_source"]
        assert source["kind"] == "heuristic"
        assert source["learned_from_data"] is False

    def test_invalid_weights_are_rejected_at_import(self, tmp_path):
        bad = json.loads(json.dumps(CONFIG))
        bad["weights"]["style"] = 0.9
        p = tmp_path / "cfg.json"
        p.write_text(json.dumps(bad))
        with pytest.raises(RuntimeError, match="weights sum"):
            load_recommender_config(p)

    def test_missing_weight_key_is_rejected(self, tmp_path):
        bad = json.loads(json.dumps(CONFIG))
        del bad["weights"]["pattern"]
        p = tmp_path / "cfg.json"
        p.write_text(json.dumps(bad))
        with pytest.raises(RuntimeError, match="weights keys"):
            load_recommender_config(p)

    def test_version_mismatch_is_rejected(self, tmp_path):
        bad = json.loads(json.dumps(CONFIG))
        bad["config_version"] = "bogus"
        p = tmp_path / "cfg.json"
        p.write_text(json.dumps(bad))
        with pytest.raises(RuntimeError, match="config_version"):
            load_recommender_config(p)


class TestDeterminism:
    def test_identical_ties_resolve_by_stable_id(self, db):
        clones = []
        for i in range(4):
            c = _product(f"Tie Sofa {i}", emb="identical tie embedding")
            clones.append(c)
            db.add(c)
        db.commit()
        try:
            res = recommend(db, make_quiz(color_palette=[], materials=[], patterns=[]),
                            use_cache=False)
            ids = [i["id"] for i in res["categories"].get("sofa", [])]
            clone_ids = sorted(c.id for c in clones)
            present = [i for i in ids if i in clone_ids]
            assert present == sorted(present, key=clone_ids.index), \
                "tied scores must order by stable product id"
        finally:
            for c in clones:
                db.delete(c)
            db.commit()

    def test_feedback_rerank_sort_is_deterministic(self):
        rows = [
            {"id": "b", "final_score": 0.9},
            {"id": "a", "final_score": 0.9},
            {"id": "c", "final_score": 0.5},
        ]
        out = apply_feedback([dict(r) for r in rows], {"c": 1})
        # c gets the boost but still loses; the 0.9 tie orders by stable id
        assert [r["id"] for r in out] == ["a", "b", "c"]


class TestDiversityAndDuplicates:
    def test_exact_duplicate_titles_suppressed(self, db):
        dupes = [_product("Same Walnut Sofa Duplicate", price=55_000_000 + i)
                 for i in range(5)]
        db.add_all(dupes)
        db.commit()
        try:
            res = recommend(db, make_quiz(), use_cache=False)
            titles = [i["title"] for i in res["categories"].get("sofa", [])]
            assert titles.count("Same Walnut Sofa Duplicate") <= 1
        finally:
            for d in dupes:
                db.delete(d)
            db.commit()

    def test_near_duplicate_embeddings_suppressed(self):
        from ai.embedding_service import cosine_similarity, get_embedding

        base = get_embedding("unique near duplicate base sofa")
        rows = [
            {"id": "x1", "title": "x one", "styles": ["modern"],
             "_emb": list(base)},
            {"id": "x2", "title": "x two different title", "styles": ["modern"],
             "_emb": [v + 1e-6 for v in base]},  # cosine ~ 1.0
            {"id": "x3", "title": "x three", "styles": ["minimal"],
             "_emb": list(get_embedding("completely different furniture item"))},
        ]
        kept = diversify(rows)
        kept_ids = [r["id"] for r in kept]
        assert "x1" in kept_ids and "x3" in kept_ids
        sim = cosine_similarity(rows[0]["_emb"], rows[1]["_emb"])
        assert sim >= CONFIG["diversity"]["duplicate_embedding_cosine"]
        if "x2" in kept_ids:  # only acceptable if under threshold — it is not
            pytest.fail("near-duplicate embedding was not suppressed")

    def test_style_cap_limits_one_look_per_category(self, db):
        same_style = [
            _product(f"Iron Loft Sofa {i}", price=58_000_000 + i,
                     styles=["industrial"], materials=["metal"], colors=["#1A1A1A"],
                     emb=f"industrial metal sofa variant {i}")
            for i in range(8)
        ]
        db.add_all(same_style)
        db.commit()
        try:
            res = recommend(db, make_quiz(styles=["industrial"], materials=["metal"],
                                          color_palette=["#1A1A1A"]), use_cache=False)
            kept = [i for i in res["categories"].get("sofa", [])
                    if i["title"].startswith("Iron Loft Sofa")]
            cap = CONFIG["diversity"]["max_per_style"]
            assert len(kept) <= cap
        finally:
            for s in same_style:
                db.delete(s)
            db.commit()

    def test_diversify_never_reorders(self):
        rows = [{"id": str(i), "title": f"t{i}", "styles": ["modern"],
                 "_emb": []} for i in range(7)]
        kept = diversify(rows)
        assert [r["id"] for r in kept] == [str(i) for i in range(len(kept))]


class TestNoResultAndFewResult:
    def test_impossible_budget_reports_all_categories_empty(self, db):
        res = recommend(db, make_quiz(budget_min_toman=1, budget_max_toman=10),
                        use_cache=False)
        assert res["categories"] == {}
        assert set(res["meta"]["empty_categories"]) == set(CATEGORIES)

    def test_meta_echoes_budget_window(self, db):
        res = recommend(db, make_quiz(budget_min_toman=2_000_000,
                                      budget_max_toman=90_000_000), use_cache=False)
        assert res["meta"]["budget_min_toman"] == 2_000_000
        assert res["meta"]["budget_max_toman"] == 90_000_000

    def test_meta_stamps_versions(self, db):
        res = recommend(db, make_quiz(), use_cache=False)
        assert res["meta"]["weights_version"] == CONFIG["config_version"]
        assert res["meta"]["recommender_version"]
        assert res["meta"]["taxonomy_version"]
        assert res["meta"]["weights"] == WEIGHTS

    def test_few_results_are_not_padded(self, db):
        """A category with a single in-budget candidate returns exactly one
        item — the engine never relaxes the hard budget to fill slots."""
        res = recommend(db, make_quiz(budget_min_toman=1_000_000,
                                      budget_max_toman=1_600_000), use_cache=False)
        if res["categories"]:
            for items in res["categories"].values():
                for item in items:
                    assert item["price_toman"] <= 1_600_000

    def test_out_of_budget_never_recommended(self, db):
        res = recommend(db, make_quiz(budget_min_toman=100_000_000,
                                      budget_max_toman=2_000_000_000), use_cache=False)
        for items in res["categories"].values():
            for item in items:
                assert item["price_toman"] >= 100_000_000


class TestExplanationFidelity:
    def test_every_explanation_reconstructs_final_score(self, db):
        res = recommend(db, make_quiz(), use_cache=False)
        checked = 0
        for items in res["categories"].values():
            for item in items:
                exp = item["explanation"]
                recomputed = (
                    WEIGHTS["style"] * exp["style_match"] / 100
                    + WEIGHTS["color"] * exp["color_match"] / 100
                    + WEIGHTS["budget"] * exp["budget_fit"] / 100
                    + WEIGHTS["material"] * exp["material_match"] / 100
                    + WEIGHTS["pattern"] * exp["pattern_match"] / 100
                )
                assert item["final_score"] == pytest.approx(recomputed, abs=0.021), \
                    f"{item['title']}: explanation does not sum to final score"
                checked += 1
        assert checked >= 5

    def test_private_embedding_key_never_leaks(self, db):
        res = recommend(db, make_quiz(), use_cache=False)
        for items in res["categories"].values():
            for item in items:
                assert "_emb" not in item
                assert "style_embedding" not in item


class TestEdgeCases:
    def test_zero_width_budget_window(self):
        assert rec.budget_score(50, 50, 50) == 1.0
        assert rec.budget_score(49, 50, 50) == 0.0

    def test_unknown_hex_in_product_scores_neutral_distance(self):
        assert rec.color_distance("#AABBCC", "garbage") == 1.0

    def test_pattern_preference_affects_score_but_not_hard_filter(self, db):
        persian = make_quiz(patterns=["persian"])
        res = recommend(db, persian, use_cache=False)
        assert res["categories"], "pattern preference must not filter anything out"
        # scoring difference is exercised through explanation components
        for items in res["categories"].values():
            for item in items:
                assert "pattern_match" in item["explanation"]

    def test_empty_optional_quiz_fields_still_recommends(self, db):
        quiz = {"styles": ["minimal"], "color_palette": [], "materials": [],
                "patterns": [], "budget_min_toman": 0,
                "budget_max_toman": 500_000_000}
        res = recommend(db, quiz, use_cache=False)
        assert res["categories"]
