"""AI stack version registry — the single source of truth for *what* produced
an extraction, an embedding or a recommendation.

Why this module exists
----------------------
Master Prompt 04: "store model, prompt, taxonomy and extraction version".
Before it, the provider/model ids lived only in ``settings``, the prompt had no
version, the taxonomy version was a JSON field nobody read, and the recommender
weights were anonymous constants. Quality regressions were unexplainable
because there was no record of which artefact versions were in play.

Everything that produces AI output stamps ``ai_version_info()`` (or a subset)
into its result, and every evidence artifact produced by the evaluation scripts
records the same stamp. A benchmark number without this stamp is not evidence.

Versioning rules
----------------
* Bump ``AI_STACK_VERSION`` when any stamped artefact below changes.
* Extraction prompt: semantic change to ``EXTRACTION_PROMPT`` bumps
  ``EXTRACTION_PROMPT_VERSION`` (``p1`` = the original baseline prompt,
  ``p2`` = current, with taxonomy-driven pattern list and review fields).
* Taxonomy: ``TAXONOMY_VERSION`` is read from ``seed_data/style_taxonomy.json``
  (additive change → minor bump; removing/renaming a stable ID → major bump and
  a migration note).
* Embeddings: ``EMBEDDING_MODEL_ID`` + ``EMBEDDING_DIM`` together identify the
  vector space. Changing either requires re-embedding the whole catalog (see
  ``docs/ai/model-versions.md`` §re-embedding).
"""
from __future__ import annotations

from app.core.config import settings

#: Coarse version of the AI stack as deployed by this branch.
AI_STACK_VERSION = "2026-08-26.1"

#: Version of the extraction prompt template in ``ai.feature_extractor``.
EXTRACTION_PROMPT_VERSION = "p2"

#: Version of the recommender configuration (weights + knobs) in
#: ``ai/recommender_config.json``. 2026-08-26.1 = Stage 1 (T-1.2): switchable,
#: validated weight profiles ("current" baseline + normalised "client-ad").
RECOMMENDER_CONFIG_VERSION = "2026-08-26.1"

#: Embedding model identity. ``clip-ViT-B/32`` via sentence-transformers
#: produces 512-d unit vectors; the deterministic hash backend mimics the
#: dimension (never the geometry — see ``ai/embedding_service.py``).
EMBEDDING_MODEL_ID = "clip-ViT-B/32"
EMBEDDING_MODEL_BACKENDS = {
    "clip": EMBEDDING_MODEL_ID,
    "hash": "feature-hash-512 (DETERMINISTIC FALLBACK — NOT a semantic model)",
}


def ai_version_info(embedding_backend: str | None = None) -> dict:
    """Assemble the version stamp embedded in results and evidence.

    ``embedding_backend`` defaults to the *configured* backend, not the
    resolved one, so the stamp never triggers a model load.
    """
    from ai.taxonomy import TAXONOMY_VERSION

    backend = embedding_backend or settings.EMBEDDING_BACKEND
    provider = settings.AI_PROVIDER
    model = {
        "gemini": settings.GEMINI_MODEL,
        "openai": settings.OPENAI_MODEL,
        "mock": "filename-heuristic (offline dev/CI only)",
    }[provider]
    return {
        "ai_stack_version": AI_STACK_VERSION,
        "extraction": {
            "provider": provider,
            "model": model,
            "prompt_version": EXTRACTION_PROMPT_VERSION,
            "taxonomy_version": TAXONOMY_VERSION,
        },
        "embedding": {
            "backend": backend,
            "model": EMBEDDING_MODEL_BACKENDS.get(backend, backend),
            "dim": settings.EMBEDDING_DIM,
        },
        "recommender_config_version": RECOMMENDER_CONFIG_VERSION,
    }
