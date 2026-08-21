"""Stage 04 remediation · production seeding is explicit, never boot-time.

Independent review of PR #9: the base compose file ran
``load_realistic_products.py --from-json`` on every backend start, so every
deployment without ``seed_data/embeddings_real.json`` (i.e. all of them — the
artefact must be generated on an egress-enabled machine) crash-looped.

Remediated contract (Option B — docs/ai/model-versions.md §5):

* the backend startup command is migrations + server, nothing else;
* catalog loading is a separate, deliberately invoked bootstrap job;
* ``--from-json`` without the artefact fails loudly with the runbook pointer;
* nothing in the production path silently falls back to hash embeddings.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import ai.embedding_service as es
from scripts.load_realistic_products import EMBEDDINGS_JSON, _precomputed

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "docker-compose.yml"


class TestFromJsonArtifactRule:
    def test_from_json_without_artifact_fails_loudly(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "scripts.load_realistic_products.EMBEDDINGS_JSON",
            tmp_path / "absent-embeddings_real.json",
        )
        with pytest.raises(SystemExit, match="embeddings_real.json"):
            _precomputed(True, strict=True)

    def test_from_json_message_points_at_the_runbook(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "scripts.load_realistic_products.EMBEDDINGS_JSON",
            tmp_path / "absent-embeddings_real.json",
        )
        with pytest.raises(SystemExit) as exc:
            _precomputed(True, strict=True)
        message = str(exc.value)
        assert "--real-embeddings" in message
        assert "model-versions.md" in message

    def test_from_json_message_never_instructs_committing_the_artifact(
        self, monkeypatch, tmp_path
    ):
        """Housekeeping regression (independent review): the strict failure
        message must guide operators to a controlled deployment artifact /
        mounted volume — never to committing embeddings_real.json, which
        tests forbid and which would bake vectors into git history."""
        monkeypatch.setattr(
            "scripts.load_realistic_products.EMBEDDINGS_JSON",
            tmp_path / "absent-embeddings_real.json",
        )
        with pytest.raises(SystemExit) as exc:
            _precomputed(True, strict=True)
        message = str(exc.value)
        lowered = message.lower()
        assert "commit the file" not in lowered
        assert "egress-enabled machine" in lowered
        assert ("artifact" in lowered or "mounted volume" in lowered)
        assert "do not commit" in lowered or "never commit" in lowered

    def test_artifact_is_not_committed(self):
        # A committed (fabricated or stale) artefact would be worse than none:
        # generation requires an egress-enabled machine and the real CLIP model.
        assert not EMBEDDINGS_JSON.exists(), (
            "seed_data/embeddings_real.json is present in the repository — it "
            "must be generated per deployment, never committed"
        )

    def test_no_silent_hash_when_artifact_missing_non_strict_warns(
        self, monkeypatch, tmp_path, caplog
    ):
        import logging

        monkeypatch.setattr(
            "scripts.load_realistic_products.EMBEDDINGS_JSON",
            tmp_path / "absent-embeddings_real.json",
        )
        with caplog.at_level(
            logging.WARNING, logger="scripts.load_realistic_products"
        ):
            result = _precomputed(True, strict=False)
        assert result == {}
        assert "embeddings_real.json" in caplog.text

    def test_production_embedding_call_never_silently_uses_hash(
        self, reset_settings
    ):
        reset_settings(APP_ENV="production", EMBEDDING_BACKEND="hash")
        es.reset_backend_resolution()
        with pytest.raises(es.EmbeddingBackendError, match="not a production backend"):
            es.get_embedding("any product description")
        es.reset_backend_resolution()


class TestComposeStartupPath:
    def test_backend_startup_command_does_not_seed(self):
        cfg = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        command = cfg["services"]["backend"]["command"]
        assert "alembic upgrade head" in command
        assert "uvicorn" in command
        assert "load_realistic_products" not in command, (
            "catalog seeding must not run on backend startup (Stage 04 "
            "remediation, Option B) — use the catalog-bootstrap job"
        )
        assert "seed_products" not in command

    def test_catalog_bootstrap_is_an_explicit_profile_job(self):
        cfg = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        job = cfg["services"]["catalog-bootstrap"]
        assert job.get("profiles") == ["bootstrap"], (
            "the bootstrap job must not run on plain `docker compose up`"
        )
        assert job.get("restart") == "no"
        assert "--from-json" in job["command"]
        assert "--if-empty" in job["command"]
        assert "--seed-demo-accounts" not in job["command"]

    def test_dev_overlay_still_seeds_without_from_json(self):
        dev = yaml.safe_load(
            (REPO_ROOT / "docker-compose.dev.yml").read_text(encoding="utf-8")
        )
        command = dev["services"]["backend"]["command"]
        assert "load_realistic_products" in command  # dev convenience retained
        assert "--from-json" not in command  # dev never requires the artefact
