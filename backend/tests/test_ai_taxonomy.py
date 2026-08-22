"""Stage 04 · taxonomy integrity, Persian labels and unknown-value behaviour.

Master Prompt 04 work item 1: "Specify taxonomy for living-room products,
styles, colors, materials, patterns, dimensions, room type and unknown values;
preserve Persian labels and stable IDs."
"""
from __future__ import annotations

import pytest

from ai import taxonomy as tax
from app.models.product import CATEGORIES as MODEL_CATEGORIES
from app.schemas.quiz import QuizIn


class TestTaxonomyIntegrity:
    def test_taxonomy_loads_and_is_versioned(self):
        assert tax.taxonomy(), "taxonomy file must load"
        assert tax.taxonomy_version() not in ("", "unknown")

    def test_validate_reports_no_problems(self):
        problems = tax.validate()
        assert problems == [], f"taxonomy integrity problems: {problems}"

    def test_style_ids_are_stable_and_unique(self):
        styles = tax.styles()
        assert len(styles) == len(set(styles))
        # Stable IDs — the v2.0 set, unchanged in 2.1 (additive release)
        assert set(styles) >= {
            "modern", "scandinavian", "industrial", "boho", "minimal", "classic"
        }

    def test_persian_labels_exist_for_every_entity(self):
        for s in tax.styles():
            assert tax.label("style", s, "fa"), f"style {s} missing name_fa"
        for m in tax.materials():
            assert tax.label("material", m, "fa"), f"material {m} missing name_fa"
        for p in tax.patterns():
            assert tax.label("pattern", p, "fa"), f"pattern {p} missing name_fa"
        for c in tax.categories():
            assert tax.label("category", c, "fa"), f"category {c} missing name_fa"

    def test_english_labels_exist_for_frontend_fallback(self):
        assert tax.label("style", "boho", "en") == "Bohemian"
        assert tax.label("pattern", "persian", "en") == "Persian"

    def test_taxonomy_categories_match_product_model(self):
        """The taxonomy is the documentation of the model constant; drift here
        would mean the recommender queries categories that don't exist."""
        assert set(tax.categories()) == set(MODEL_CATEGORIES)

    def test_patterns_taxonomy_covers_extractor_allowlist(self):
        from ai.feature_extractor import ALLOWED_PATTERNS

        assert set(ALLOWED_PATTERNS) == set(tax.patterns())

    def test_unknown_value_policy_is_declared(self):
        policy = tax.unknown_value_policy()
        assert "neutral_score" in policy and policy["neutral_score"] == 0.5


class TestUnknownValues:
    def test_unknown_style_is_not_known(self):
        assert not tax.is_known("style", "artdeco")
        assert tax.is_known("style", "modern")

    def test_label_returns_none_for_unknown_id(self):
        assert tax.label("style", "nope") is None
        assert tax.label("material", "unobtainium") is None

    def test_clamp_to_taxonomy_splits_known_and_unknown(self):
        known, unknown = tax.clamp_to_taxonomy(["wood", "carbonite"], "material")
        assert known == ["wood"]
        assert unknown == ["carbonite"]

    def test_quiz_rejects_unknown_pattern(self):
        with pytest.raises(Exception):
            QuizIn(styles=["modern"], room_width_cm=400, room_length_cm=500,
                   budget_min_toman=0, budget_max_toman=100, patterns=["checks"])

    def test_quiz_rejects_malformed_color(self):
        with pytest.raises(Exception):
            QuizIn(styles=["modern"], room_width_cm=400, room_length_cm=500,
                   budget_min_toman=0, budget_max_toman=100, color_palette=["red"])

    def test_quiz_accepts_empty_optionals_as_no_preference(self):
        q = QuizIn(styles=["modern"], room_width_cm=400, room_length_cm=500,
                   budget_min_toman=0, budget_max_toman=100)
        assert q.materials == [] and q.patterns == [] and q.color_palette == []

    def test_quiz_rejects_unknown_style_and_material(self):
        with pytest.raises(Exception):
            QuizIn(styles=["futurist"], room_width_cm=400, room_length_cm=500,
                   budget_min_toman=0, budget_max_toman=100)
        with pytest.raises(Exception):
            QuizIn(styles=["modern"], room_width_cm=400, room_length_cm=500,
                   budget_min_toman=0, budget_max_toman=100, materials=["bamboo"])

    def test_room_dimensions_have_bounds(self):
        with pytest.raises(Exception):
            QuizIn(styles=["modern"], room_width_cm=50, room_length_cm=500,
                   budget_min_toman=0, budget_max_toman=100)
        with pytest.raises(Exception):
            QuizIn(styles=["modern"], room_width_cm=400, room_length_cm=9_999,
                   budget_min_toman=0, budget_max_toman=100)

    def test_budget_ordering_enforced(self):
        with pytest.raises(Exception):
            QuizIn(styles=["modern"], room_width_cm=400, room_length_cm=500,
                   budget_min_toman=100, budget_max_toman=100)


class TestExtractorClamping:
    def test_sanitize_discards_unknown_taxonomy_values(self):
        from ai.feature_extractor import _sanitize

        out = _sanitize({
            "style": ["modern", "spaceage"],
            "material": ["wood", "dilithium"],
            "patterns": ["persian"],
            "colors": ["#AABBCC", "not-a-color"],
            "confidence": 0.9,
        })
        assert out["style"] == ["modern"]
        assert out["material"] == ["wood"]
        assert out["patterns"] == ["persian"]
        assert out["colors"] == ["#AABBCC"]
        assert sorted(out["unknown_taxonomy_values"]) == ["dilithium", "spaceage"]

    def test_unknown_extraction_values_force_review(self):
        from ai.extraction_review import review_decision

        decision = review_decision({
            "confidence": 0.95, "style": ["modern"], "material": ["wood"],
            "unknown_taxonomy_values": ["dilithium"],
        })
        assert decision["needs_review"]
        assert "unknown_taxonomy_values" in decision["review_reasons"]
