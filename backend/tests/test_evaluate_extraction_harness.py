"""Harness-level contracts of ``scripts/evaluate_extraction.py`` (A5, 2026-09-07).

No provider is called. These pin two things that bit the project once:

* a MOCK run must never overwrite the committed REAL artefact
  (``docs/reports/extraction_report.json`` is release evidence);
* the rank-1 style metric must be derived from the same scoring rule as the
  headline, so the "hedge gain" number is exactly headline − rank-1.
"""
from __future__ import annotations

import json

import pytest

import scripts.evaluate_extraction as harness


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestArtefactGuard:
    def test_real_run_may_overwrite_anything(self, tmp_path):
        target = tmp_path / "extraction_report.json"
        _write(target, {"mode": "REAL:gemini", "is_mock": False})
        assert harness.protected_report_path(target, is_mock=False) == target

    def test_mock_run_is_redirected_away_from_a_real_artefact(self, tmp_path):
        target = tmp_path / "extraction_report.json"
        _write(target, {"mode": "REAL:gemini", "is_mock": False})
        assert harness.protected_report_path(target, is_mock=True) == (
            tmp_path / "extraction_report.mock.json"
        )

    def test_mock_run_overwrites_a_mock_artefact(self, tmp_path):
        target = tmp_path / "extraction_report.json"
        _write(target, {"mode": "MOCK", "is_mock": True})
        assert harness.protected_report_path(target, is_mock=True) == target

    def test_missing_or_unreadable_artefact_is_not_protected(self, tmp_path):
        missing = tmp_path / "nope.json"
        assert harness.protected_report_path(missing, is_mock=True) == missing
        garbage = tmp_path / "garbage.json"
        garbage.write_text("{not json", encoding="utf-8")
        assert harness.protected_report_path(garbage, is_mock=True) == garbage

    def test_committed_artefact_is_a_real_run_and_therefore_guarded(self):
        # The guard only matters if the file it protects is what we think it is.
        if not harness.REPORT.is_file():
            pytest.skip("no committed artefact")
        assert harness.protected_report_path(harness.REPORT, is_mock=True) != harness.REPORT


class TestScoringRule:
    truth = {"style": ["scandinavian"], "material": ["wood"]}

    def test_hedge_is_rewarded_by_the_contract_term(self):
        hedged = harness.score_item({"style": ["modern", "scandinavian"], "material": ["wood"]}, self.truth)
        rank1 = harness.score_item({"style": ["modern"], "material": ["wood"]}, self.truth)
        assert hedged == 1.0 and rank1 == 0.5  # the exact +0.5 a wrong-first hedge buys

    def test_material_is_precision_only(self):
        assert harness.score_item({"style": ["scandinavian"], "material": ["wood", "glass"]}, self.truth) == 0.75
        assert harness.score_item({"style": ["scandinavian"], "material": []}, self.truth) == 0.5

    def test_micro_prf_counts(self):
        prf = harness._prf([({"modern", "scandinavian"}, {"scandinavian"}), ({"boho"}, {"boho"})])
        assert (prf["tp"], prf["fp"], prf["fn"]) == (2, 1, 0)
        assert prf["precision"] == pytest.approx(2 / 3, abs=1e-4) and prf["recall"] == 1.0
