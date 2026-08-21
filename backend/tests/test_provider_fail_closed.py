"""Stage 04 remediation · production fail-closed provider selection.

Independent review of PR #9 found that ``FeatureExtractor`` silently fell
back to ``MockProvider`` when a real provider was selected without its key —
including in production, where the keyword heuristic's 0.9 confidence could
pass the review gate. These tests pin the remediated behaviour:

  1.  production + ``AI_PROVIDER=mock`` is rejected;
  2.  production + gemini without GEMINI_API_KEY is rejected;
  3.  production + gemini with only OPENAI_API_KEY is rejected (keys are not
      interchangeable);
  4.  production + openai without OPENAI_API_KEY is rejected;
  5.  production + openai with only GEMINI_API_KEY is rejected;
  6.  development + mock stays allowed;
  7.  development fallback is labelled ``provider="mock-fallback"``;
  8.  development fallback confidence is capped at 0.30;
  9.  production provider failure produces an empty flagged result;
  10. no production mock/fallback output can reach ``needs_review=False``;
  11. a real-provider response with confidence >= 0.80 and no failure
      markers still auto-accepts;
  12. unknown taxonomy values still force review.

No external API is called: real providers are stubbed, and key values are
obvious placeholders.
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
    MockProvider,
    OpenAIProvider,
    ProviderConfigurationError,
)
from app.core.config import Settings, ai_provider_problems

# Obvious placeholders — never real credentials.
K_GEMINI = "test-gemini-key-placeholder"
K_OPENAI = "test-openai-key-placeholder"

URL = "https://example.com/07-industrial-iron-bookshelf.jpg"


def _cfg(**overrides) -> Settings:
    base = dict(
        APP_ENV="production",
        SECRET_KEY="s" * 48,
        REDIS_URL="redis://redis:6379/0",
        COOKIE_SECURE=True,
        FRONTEND_ORIGIN="https://app.example.com",
        FERNET_KEY="2xLmTPRPYxxLW8mM3jXfKcXo5G3iVYkYfQ2vYbFsC8Y=",
        STORAGE_BACKEND="s3",
        SEED_DEMO_ACCOUNTS=False,
    )
    base.update(overrides)
    return Settings(**base)


# --------------------------------------------------------------- rule itself

class TestAuthoritativeRule:
    def test_production_mock_is_rejected(self):  # case 1
        problems = ai_provider_problems(
            "mock", has_gemini_key=True, has_openai_key=True, production=True
        )
        assert problems and "AI_PROVIDER=mock" in problems[0]

    def test_production_gemini_without_its_key_is_rejected(self):  # case 2
        problems = ai_provider_problems(
            "gemini", has_gemini_key=False, has_openai_key=False, production=True
        )
        assert problems == [
            "AI_PROVIDER=gemini requires GEMINI_API_KEY to be set — an API key "
            "for a different provider is not accepted; set GEMINI_API_KEY or "
            "use AI_PROVIDER=mock in development/test only"
        ]

    def test_production_gemini_with_only_openai_key_is_rejected(self):  # case 3
        problems = ai_provider_problems(
            "gemini", has_gemini_key=False, has_openai_key=True, production=True
        )
        assert problems and "GEMINI_API_KEY" in problems[0]

    def test_production_openai_without_its_key_is_rejected(self):  # case 4
        problems = ai_provider_problems(
            "openai", has_gemini_key=False, has_openai_key=False, production=True
        )
        assert problems and "OPENAI_API_KEY" in problems[0]

    def test_production_openai_with_only_gemini_key_is_rejected(self):  # case 5
        problems = ai_provider_problems(
            "openai", has_gemini_key=True, has_openai_key=False, production=True
        )
        assert problems and "OPENAI_API_KEY" in problems[0]

    def test_matched_provider_and_key_passes(self):
        assert ai_provider_problems(
            "gemini", has_gemini_key=True, has_openai_key=False, production=True
        ) == []
        assert ai_provider_problems(
            "openai", has_gemini_key=False, has_openai_key=True, production=True
        ) == []

    def test_mock_is_allowed_outside_production(self):  # case 6 (rule level)
        assert ai_provider_problems(
            "mock", has_gemini_key=False, has_openai_key=False, production=False
        ) == []

    def test_unknown_provider_name_is_rejected(self):
        problems = ai_provider_problems(
            "azure", has_gemini_key=True, has_openai_key=True, production=True
        )
        assert problems and "not one of" in problems[0]

    def test_error_messages_never_contain_key_values(self):
        for provider, gem, oai in (
            ("gemini", False, True), ("openai", True, False), ("mock", True, True),
        ):
            for problem in ai_provider_problems(
                provider, has_gemini_key=gem, has_openai_key=oai, production=True
            ):
                assert K_GEMINI not in problem and K_OPENAI not in problem


# ------------------------------------------------------- startup validation

class TestStartupValidation:
    def test_validate_runtime_rejects_production_mock(self, monkeypatch):
        cfg = _cfg(AI_PROVIDER="mock", GEMINI_API_KEY=K_GEMINI)
        with pytest.raises(RuntimeError, match="AI_PROVIDER=mock"):
            cfg.validate_runtime()

    def test_validate_runtime_rejects_gemini_without_key(self):
        cfg = _cfg(AI_PROVIDER="gemini")
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            cfg.validate_runtime()

    def test_validate_runtime_rejects_gemini_with_only_openai_key(self):
        cfg = _cfg(AI_PROVIDER="gemini", OPENAI_API_KEY=K_OPENAI)
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            cfg.validate_runtime()

    def test_validate_runtime_rejects_openai_with_only_gemini_key(self):
        cfg = _cfg(AI_PROVIDER="openai", GEMINI_API_KEY=K_GEMINI)
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            cfg.validate_runtime()

    def test_validate_runtime_accepts_matched_production_config(self):
        _cfg(AI_PROVIDER="gemini", GEMINI_API_KEY=K_GEMINI).validate_runtime()
        _cfg(AI_PROVIDER="openai", OPENAI_API_KEY=K_OPENAI).validate_runtime()


# ------------------------------------------------- extractor construction

class TestExtractorConstruction:
    def test_production_mock_construction_fails_closed(self, reset_settings):
        reset_settings(APP_ENV="production", AI_PROVIDER="mock")
        with pytest.raises(ProviderConfigurationError, match="AI_PROVIDER=mock"):
            FeatureExtractor()

    def test_production_gemini_without_key_fails_closed(self, reset_settings):
        reset_settings(
            APP_ENV="production", AI_PROVIDER="gemini",
            GEMINI_API_KEY="", OPENAI_API_KEY="",
        )
        with pytest.raises(ProviderConfigurationError, match="GEMINI_API_KEY"):
            FeatureExtractor()

    def test_production_gemini_with_only_openai_key_fails_closed(
        self, reset_settings
    ):
        reset_settings(
            APP_ENV="production", AI_PROVIDER="gemini",
            GEMINI_API_KEY="", OPENAI_API_KEY=K_OPENAI,
        )
        with pytest.raises(ProviderConfigurationError, match="GEMINI_API_KEY"):
            FeatureExtractor()

    def test_production_openai_without_key_fails_closed(self, reset_settings):
        reset_settings(
            APP_ENV="production", AI_PROVIDER="openai",
            GEMINI_API_KEY="", OPENAI_API_KEY="",
        )
        with pytest.raises(ProviderConfigurationError, match="OPENAI_API_KEY"):
            FeatureExtractor()

    def test_production_openai_with_only_gemini_key_fails_closed(
        self, reset_settings
    ):
        reset_settings(
            APP_ENV="production", AI_PROVIDER="openai",
            GEMINI_API_KEY=K_GEMINI, OPENAI_API_KEY="",
        )
        with pytest.raises(ProviderConfigurationError, match="OPENAI_API_KEY"):
            FeatureExtractor()

    def test_development_mock_remains_allowed(self, reset_settings):
        reset_settings(APP_ENV="development", AI_PROVIDER="mock")
        extractor = FeatureExtractor()
        assert extractor.provider.name == "mock"
        result = extractor.extract(URL)
        assert result["provider"] == "mock"  # honest label, not a fallback

    def test_production_matched_provider_constructs_the_real_one(
        self, reset_settings, monkeypatch
    ):
        reset_settings(
            APP_ENV="production", AI_PROVIDER="gemini", GEMINI_API_KEY=K_GEMINI
        )
        assert isinstance(FeatureExtractor().provider, GeminiProvider)
        reset_settings(
            APP_ENV="production", AI_PROVIDER="openai", OPENAI_API_KEY=K_OPENAI
        )
        assert isinstance(FeatureExtractor().provider, OpenAIProvider)


# ------------------------------------------------------- fallback isolation

class TestFallbackIsolation:
    def test_dev_misconfigured_provider_is_labelled_mock_fallback(
        self, reset_settings
    ):  # case 7
        reset_settings(
            APP_ENV="development", AI_PROVIDER="gemini",
            GEMINI_API_KEY="", OPENAI_API_KEY=K_OPENAI,
        )
        result = FeatureExtractor().extract(URL)
        assert result["provider"] == "mock-fallback"
        assert "GEMINI_API_KEY" in result["provider_config_error"]
        assert result["needs_review"]
        assert "fallback_provider" in result["review_reasons"]

    def test_dev_fallback_confidence_is_capped(self, reset_settings):  # case 8
        reset_settings(
            APP_ENV="development", AI_PROVIDER="gemini", GEMINI_API_KEY=""
        )
        # The heuristic itself yields 0.9 here (style+material keywords both
        # present) — the cap must pull it down to 0.30.
        result = FeatureExtractor().extract(URL)
        assert result["confidence"] <= FALLBACK_CONFIDENCE_CAP
        assert result["needs_review"]

    def test_dev_provider_failure_is_labelled_mock_fallback(
        self, monkeypatch, reset_settings
    ):
        reset_settings(
            APP_ENV="development", AI_PROVIDER="gemini", GEMINI_API_KEY=K_GEMINI
        )
        monkeypatch.setattr(
            "ai.feature_extractor.GeminiProvider.extract",
            lambda self, url: (_ for _ in ()).throw(RuntimeError("boom 503")),
        )
        result = FeatureExtractor().extract(URL)
        assert result["provider"] == "mock-fallback"
        assert "boom 503" in result["provider_error"]
        assert result["confidence"] <= FALLBACK_CONFIDENCE_CAP
        assert result["needs_review"]

    def test_production_provider_failure_produces_empty_flagged_output(
        self, monkeypatch, reset_settings
    ):  # case 9
        reset_settings(
            APP_ENV="production", AI_PROVIDER="gemini", GEMINI_API_KEY=K_GEMINI
        )
        monkeypatch.setattr(
            "ai.feature_extractor.GeminiProvider.extract",
            lambda self, url: (_ for _ in ()).throw(RuntimeError("quota exceeded")),
        )
        result = FeatureExtractor().extract(URL)
        assert result["provider"] == "failed"
        assert result["style"] == [] and result["material"] == []
        assert result["colors"] == [] and result["patterns"] == []
        assert result["confidence"] == 0.0
        assert result["needs_review"]
        assert "quota exceeded" in result["provider_error"]

    def test_production_never_auto_accepts_mock_or_fallback_output(
        self, reset_settings
    ):  # case 10 — the layered invariant, exercised end-to-end
        reset_settings(APP_ENV="production")
        # (a) the gate itself rejects mock-fallback payloads at any confidence
        decision = review_decision({
            "confidence": 1.0, "style": ["modern"], "material": ["wood"],
            "provider": "mock-fallback",
        })
        assert decision["needs_review"]
        # (b) the extractor's defence-in-depth converts any mock-derived
        # payload into an empty flagged failure in production — even when a
        # mock provider was injected past the constructor on purpose.
        ex = FeatureExtractor.__new__(FeatureExtractor)
        ex.provider = MockProvider()
        ex._fallback_problem = None
        result = ex.extract(URL)
        assert result["provider"] == "failed"
        assert result["needs_review"]
        assert result["style"] == [] and result["material"] == []
        assert result["confidence"] == 0.0

    def test_mock_fallback_reason_appears_even_above_threshold(self):
        decision = review_decision({
            "confidence": 1.0, "style": ["modern"], "material": ["wood"],
            "provider": "mock-fallback",
        })
        assert decision["needs_review"]
        assert "fallback_provider" in decision["review_reasons"]


# ------------------------------------------------------------ gate is intact

class TestGeminiModelDefault:
    """Stage 04 remediation (IR-AI-004): the retired default must not return."""

    def test_default_is_not_a_retired_model(self):
        assert Settings().GEMINI_MODEL == "gemini-3.5-flash"
        assert Settings().GEMINI_MODEL not in Settings.RETIRED_GEMINI_MODELS

    def test_retired_default_is_rejected_in_every_environment(self):
        from app.core.config import Settings as S

        for env in ("development", "test", "production"):
            cfg = S(APP_ENV=env, GEMINI_MODEL="gemini-2.0-flash", SECRET_KEY="s" * 48)
            with pytest.raises(RuntimeError, match="GEMINI_MODEL.*shut down"):
                cfg.validate_runtime()

    @pytest.mark.parametrize("retired", sorted(Settings.RETIRED_GEMINI_MODELS))
    def test_every_retired_id_is_refused(self, retired):
        cfg = Settings(APP_ENV="development", GEMINI_MODEL=retired)
        with pytest.raises(RuntimeError, match="GEMINI_MODEL"):
            cfg.validate_runtime()

    def test_active_model_passes_validation(self):
        Settings(APP_ENV="development", GEMINI_MODEL="gemini-3.5-flash").validate_runtime()


class TestGateStillWorks:
    def test_real_provider_high_confidence_still_auto_accepts(self):  # case 11
        decision = review_decision({
            "confidence": AUTO_ACCEPT_THRESHOLD,
            "style": ["modern"],
            "material": ["wood"],
            "provider": "gemini",
            "model": "gemini-2.5-flash-lite",
            "provider_error": None,
            "unknown_taxonomy_values": [],
        })
        assert decision["state"] == "auto_accept"
        assert not decision["needs_review"]

    def test_unknown_taxonomy_values_still_force_review(self):  # case 12
        decision = review_decision({
            "confidence": 0.95,
            "style": ["modern"],
            "material": ["wood"],
            "unknown_taxonomy_values": ["art-deco"],
        })
        assert decision["needs_review"]
        assert "unknown_taxonomy_values" in decision["review_reasons"]
