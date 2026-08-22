"""Stage 04 remediation · startup embedding validation (IR-AI-001 wiring).

Independent review of PR #9: ``validate_embedding_runtime()`` existed but was
never called from the application lifespan, so a production process could
start serving recommendations on whatever backend ``get_embedding`` silently
resolved to. These tests prove the wiring and the fail-closed direction:

* production lifespan invokes the validation before serving;
* production + ``EMBEDDING_BACKEND=hash`` prevents startup;
* production + unloadable CLIP prevents startup;
* a probe embedding of the wrong dimension/normalization prevents startup;
* development/test startup stays side-effect-free (no model load, no raise).

No Hugging Face weights are downloaded: CLIP-unavailable is exactly the real
sandbox/CI condition under test, and probe checks stub the embedding call.
"""
from __future__ import annotations

import asyncio

import pytest

import ai.embedding_service as es
from ai.embedding_service import EmbeddingBackendError, validate_embedding_runtime

# Import the app module at collection time, *before* any test mutates the
# live settings object: app.main runs Settings.validate_runtime() once at
# import, and that must see the normal dev/test configuration.
from app.main import lifespan


@pytest.fixture(autouse=True)
def _fresh_backend_resolution():
    """Never leak a cached backend resolution between tests."""
    es.reset_backend_resolution()
    yield
    es.reset_backend_resolution()


def _run_lifespan():
    """Run the app lifespan startup (and immediate shutdown) synchronously."""
    async def _go():
        async with lifespan(None):
            pass

    asyncio.run(_go())


def _patch_production_startup_deps(monkeypatch):
    """Neutralise the *other* production startup checks (DB-dependent)."""
    monkeypatch.setattr(
        "app.core.demo_seed.assert_no_demo_accounts_in_production",
        lambda db: None,
    )

    class _FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def close(self):
            pass

    monkeypatch.setattr("app.db.session.SessionLocal", _FakeSession)


class TestLifespanWiring:
    def test_production_lifespan_validates_embedding_runtime(
        self, monkeypatch, reset_settings
    ):
        reset_settings(APP_ENV="production", EMBEDDING_BACKEND="hash")
        _patch_production_startup_deps(monkeypatch)
        calls: list[dict] = []
        monkeypatch.setattr(
            "ai.embedding_service.validate_embedding_runtime",
            lambda: calls.append({"backend": "clip"}) or {"backend": "clip"},
        )
        _run_lifespan()
        assert calls, "production lifespan must call validate_embedding_runtime"

    def test_development_lifespan_skips_embedding_validation(
        self, monkeypatch, reset_settings
    ):
        reset_settings(APP_ENV="development", EMBEDDING_BACKEND="hash")
        calls: list[dict] = []
        monkeypatch.setattr(
            "ai.embedding_service.validate_embedding_runtime",
            lambda: calls.append({}) or {},
        )
        _run_lifespan()  # must not raise and must not resolve a backend
        assert calls == []

    def test_production_hash_backend_prevents_serving(
        self, monkeypatch, reset_settings
    ):
        reset_settings(APP_ENV="production", EMBEDDING_BACKEND="hash")
        _patch_production_startup_deps(monkeypatch)
        with pytest.raises(EmbeddingBackendError, match="not a production backend"):
            _run_lifespan()

    def test_production_clip_unavailable_prevents_serving(
        self, monkeypatch, reset_settings
    ):
        reset_settings(APP_ENV="production", EMBEDDING_BACKEND="clip")
        _patch_production_startup_deps(monkeypatch)
        with pytest.raises(EmbeddingBackendError, match="refusing to continue"):
            _run_lifespan()


class TestRuntimeSelfCheck:
    def test_wrong_dimension_probe_fails_validation(self, monkeypatch, reset_settings):
        reset_settings(APP_ENV="development", EMBEDDING_BACKEND="hash")
        monkeypatch.setattr(es, "get_embedding", lambda text, image_path=None: [0.1] * 64)
        with pytest.raises(EmbeddingBackendError, match="self-check"):
            validate_embedding_runtime()

    def test_unnormalized_probe_fails_validation(
        self, monkeypatch, reset_settings
    ):
        reset_settings(APP_ENV="development", EMBEDDING_BACKEND="hash")
        vec = [0.5] * es.EMBEDDING_DIM  # norm != 1
        monkeypatch.setattr(es, "get_embedding", lambda text, image_path=None: vec)
        with pytest.raises(EmbeddingBackendError, match="not L2-normalized"):
            validate_embedding_runtime()

    def test_dev_hash_runtime_passes_with_self_check(self, reset_settings):
        reset_settings(APP_ENV="development", EMBEDDING_BACKEND="hash")
        info = validate_embedding_runtime()
        assert info["backend"] == "hash"
        assert info["self_check"] == "passed"
        assert info["dim"] == es.EMBEDDING_DIM

    def test_actionable_message_names_the_runbook(self, monkeypatch, reset_settings):
        reset_settings(APP_ENV="development", EMBEDDING_BACKEND="hash")
        monkeypatch.setattr(es, "get_embedding", lambda text, image_path=None: [1.0])
        with pytest.raises(EmbeddingBackendError, match="docs/ai/model-versions.md"):
            validate_embedding_runtime()
