"""Stage 04 · embedding safety: no silent hash fallback in production,
dimension/normalization verification, version identity.

Master Prompt 04 work item 7: "Ensure embeddings are real in Production,
dimension-compatible, normalized and never silently replaced by hash fallback."
"""
from __future__ import annotations

import math

import pytest

import ai.embedding_service as es
from ai.model_registry import EMBEDDING_MODEL_ID, ai_version_info


@pytest.fixture(autouse=True)
def _reset_backend_cache():
    es._backend = None
    yield
    es._backend = None


class TestHashBackendBaselines:
    def test_hash_embeddings_are_512d_and_unit_norm(self):
        vec = es.get_embedding("a modern walnut coffee table")
        assert not es.verify_embedding(vec)

    def test_hash_embeddings_are_deterministic(self):
        a = es.get_embedding("the same sentence")
        b = es.get_embedding("the same sentence")
        assert a == b

    def test_verify_embedding_catches_wrong_dimension(self):
        assert any("dimension" in p for p in es.verify_embedding([0.1] * 511))

    def test_verify_embedding_catches_unnormalized_vector(self):
        vec = [x * 2 for x in es.get_embedding("scaled")]
        assert any("normalized" in p for p in es.verify_embedding(vec))

    def test_verify_embedding_catches_nan_and_none(self):
        vec = es.get_embedding("nan test")
        vec[3] = float("nan")
        assert any("NaN" in p for p in es.verify_embedding(vec))
        assert es.verify_embedding(None) == ["embedding is None"]


class TestProductionFailSafe:
    def test_production_refuses_clip_unavailable(self, reset_settings):
        """CLIP cannot load without sentence-transformers/torch — in production
        that must raise, never silently rank on hash vectors."""
        reset_settings(APP_ENV="production", EMBEDDING_BACKEND="clip")
        with pytest.raises(es.EmbeddingBackendError, match="refusing"):
            es.get_backend()

    def test_production_refuses_configured_hash(self, reset_settings):
        """Even an explicit EMBEDDING_BACKEND=hash is a development backend;
        production boot must fail loudly (policy: docs/ai/model-versions.md)."""
        reset_settings(APP_ENV="production", EMBEDDING_BACKEND="hash")
        with pytest.raises(es.EmbeddingBackendError, match="hash is not a production backend"):
            es.get_backend()

    def test_production_get_embedding_fails_not_falls_back(self, reset_settings):
        reset_settings(APP_ENV="production", EMBEDDING_BACKEND="clip")
        with pytest.raises(es.EmbeddingBackendError):
            es.get_embedding("anything")

    def test_validate_embedding_runtime_same_rules(self, reset_settings):
        reset_settings(APP_ENV="production", EMBEDDING_BACKEND="hash")
        with pytest.raises(es.EmbeddingBackendError):
            es.validate_embedding_runtime()

    def test_development_still_falls_back_with_label(self, reset_settings):
        reset_settings(APP_ENV="development", EMBEDDING_BACKEND="clip")
        assert es.get_backend() == "hash"  # CLIP not installed in CI
        info = es.validate_embedding_runtime()
        assert info["backend"] == "hash"
        assert "NOT a semantic model" in info["model"]

    def test_test_environment_uses_hash(self):
        assert es.get_backend() == "hash"


class TestVersionIdentity:
    def test_registry_reports_embedding_identity(self):
        info = ai_version_info(embedding_backend="hash")
        assert info["embedding"]["dim"] == 512
        assert info["embedding"]["backend"] == "hash"
        assert "FALLBACK" in info["embedding"]["model"]

    def test_clip_identity_is_declared(self):
        info = ai_version_info(embedding_backend="clip")
        assert info["embedding"]["model"] == EMBEDDING_MODEL_ID

    def test_version_info_includes_extraction_and_recommender(self):
        info = ai_version_info()
        assert info["extraction"]["prompt_version"]
        assert info["extraction"]["taxonomy_version"] not in ("", "unknown")
        assert info["recommender_config_version"]

    def test_cosine_similarity_symmetric_and_bounded(self):
        a = es.get_embedding("modern sofa")
        b = es.get_embedding("modern sofa metal legs")
        assert math.isclose(es.cosine_similarity(a, b), es.cosine_similarity(b, a))
        assert -1.0 <= es.cosine_similarity(a, b) <= 1.0
        assert es.cosine_similarity(a, a) == pytest.approx(1.0)
