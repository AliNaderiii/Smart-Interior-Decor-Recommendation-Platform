"""Review gate vs the committed REAL benchmark (A5, 2026-09-07).

Two contracts:

1. ``ambiguous_style`` — a multi-style answer confined to one confusable
   cluster is pre-flagged; a single style, a cross-cluster pair or a
   non-cluster pair is not.
2. Replay — the current gate, replayed over the per-item predictions in
   ``docs/reports/extraction_report.json`` (gemini-3.5-flash-lite, prompt p5),
   lets **no** style miss through unflagged. If a future prompt/model changes
   the failure signature, this test is the tripwire: fix the gate or the
   artefact together, deliberately.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai.extraction_review import (
    AMBIGUOUS_STYLE_CLUSTERS,
    ambiguous_style,
    review_decision,
)

REPO = Path(__file__).resolve().parents[2]
ARTEFACT = REPO / "docs" / "reports" / "extraction_report.json"
BENCHMARK = REPO / "backend" / "tests" / "benchmark_50_images.json"


class TestAmbiguousStyleRule:
    def test_cluster_is_the_documented_one(self):
        assert frozenset({"modern", "scandinavian", "minimal"}) in AMBIGUOUS_STYLE_CLUSTERS

    @pytest.mark.parametrize("styles", [
        ["modern", "scandinavian"],
        ["scandinavian", "minimal"],
        ["minimal", "modern"],
        ["modern", "minimal", "scandinavian"],
    ])
    def test_hedge_inside_the_cluster_is_ambiguous(self, styles):
        assert ambiguous_style(styles)

    @pytest.mark.parametrize("styles", [
        ["modern"],                      # single answer: committed, not hedging
        ["scandinavian"],
        ["boho", "scandinavian"],        # cross-cluster: a real blend
        ["industrial", "modern"],
        ["classic", "boho"],             # outside the cluster entirely
        [],
        ["modern", "modern"],            # duplicates are one style
        None,
        "modern",                        # scalar: not a list, never ambiguous
    ])
    def test_everything_else_is_not(self, styles):
        assert not ambiguous_style(styles)

    def test_gate_flags_with_a_machine_readable_reason(self):
        decision = review_decision({
            "confidence": 0.95, "style": ["modern", "scandinavian"], "material": ["wood"],
        })
        assert decision["needs_review"] is True
        assert decision["review_reasons"] == ["ambiguous_style"]

    def test_committed_single_style_at_high_confidence_still_auto_accepts(self):
        decision = review_decision({
            "confidence": 0.95, "style": ["scandinavian"], "material": ["wood"],
        })
        assert decision["state"] == "auto_accept"

    def test_cross_cluster_blend_is_not_penalised(self):
        decision = review_decision({
            "confidence": 0.9, "style": ["boho", "scandinavian"], "material": ["rattan"],
        })
        assert decision["state"] == "auto_accept"


@pytest.mark.skipif(not ARTEFACT.is_file(), reason="benchmark artefact not present")
class TestReplayAgainstRealBenchmark:
    @pytest.fixture(scope="class")
    def replay(self):
        import scripts.audit_review_gate as audit

        report = json.loads(ARTEFACT.read_text(encoding="utf-8"))
        assert str(report["mode"]).startswith("REAL"), "artefact must be a REAL run"
        truth = {i["id"]: i for i in json.loads(BENCHMARK.read_text(encoding="utf-8"))["items"]}
        return audit.replay(report, truth)

    def test_artefact_is_the_p5_gemini_run(self):
        report = json.loads(ARTEFACT.read_text(encoding="utf-8"))
        assert report["versions"]["extraction"]["prompt_version"] == "p5"
        assert report["images"] == 50 and report["mean_accuracy"] >= 0.80

    def test_run_time_gate_flagged_nothing(self, replay):
        # The finding that motivated ambiguous_style: confidence alone caught 0.
        assert replay["flagged_by_artefact"] == 0

    def test_no_style_miss_passes_unflagged(self, replay):
        assert replay["unflagged_style_misses"] == []
        assert replay["passed_unflagged"]["style_hit"] == replay["passed_unflagged"]["n"]

    def test_gate_does_not_flag_everything(self, replay):
        # A gate that flags all 50 would be "safe" and useless.
        assert 15 <= replay["passed_unflagged"]["n"] <= 35
        assert replay["reason_frequency"] == {"ambiguous_style": replay["flagged_by_current_gate"]}

    def test_flagged_set_is_where_the_errors_live(self, replay):
        flagged, passed = replay["flagged"], replay["passed_unflagged"]
        assert flagged["mean_score"] < passed["mean_score"]
        assert flagged["style_hit"] < flagged["n"]
