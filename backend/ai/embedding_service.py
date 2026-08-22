"""Embedding service — CLIP ViT-B/32 with an offline deterministic fallback.

Backends (settings.EMBEDDING_BACKEND):
  * ``clip`` — loads ``clip-ViT-B/32`` via sentence-transformers (512-dim),
    cached in memory after the first call. Supports text and images.
  * ``hash`` — deterministic feature-hash embedding (512-dim). Used when the
    model can't be downloaded (offline/CI) and for unit tests. Same API,
    stable cosine geometry: similar texts share token buckets so similarity
    is still meaningful for our tag-based descriptions.

Production safety (Stage 04, Master Prompt 04 work item 7)
----------------------------------------------------------
Historically the fallback was *automatic everywhere*: if CLIP failed to load
(no internet, no torch), the service logged a warning and silently switched to
hash — in Production that means the semantic stage of the recommender runs on
fake geometry while every dashboard still shows green. That is now a hard
error:

* ``APP_ENV=production`` + ``EMBEDDING_BACKEND=clip`` + CLIP unavailable →
  :class:`EmbeddingBackendError` (never a silent hash).
* ``APP_ENV=production`` + ``EMBEDDING_BACKEND=hash`` → same error: hash is a
  dev/test backend by policy (``docs/ai/model-versions.md``); a deliberate
  production downgrade must be a documented decision, not a config default.

``validate_embedding_runtime()`` performs the same checks eagerly and is
intended for startup wiring (integration request IR-AI-001 wires it into the
application lifespan; the module-level guard already protects every call).
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
import threading
from typing import Optional

from ai.model_registry import EMBEDDING_MODEL_BACKENDS, EMBEDDING_MODEL_ID
from app.core.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_DIM = settings.EMBEDDING_DIM  # 512, matches CLIP ViT-B/32

EMBEDDING_MODEL = EMBEDDING_MODEL_ID  #: semantic identity of the vector space

#: Tolerance for the unit-norm check in :func:`verify_embedding`.
NORM_TOLERANCE = 1e-3


class EmbeddingBackendError(RuntimeError):
    """Raised when Production would otherwise silently run on hash vectors."""


_model = None
_model_lock = threading.Lock()
_backend: str | None = None


def _load_clip():
    """Load CLIP once, thread-safe; return None if unavailable."""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer("clip-ViT-B-32")
            logger.info("CLIP ViT-B/32 loaded and cached in memory")
        except Exception as exc:  # pragma: no cover - env dependent
            logger.warning(
                "CLIP unavailable (%s). Hash fallback would be used outside "
                "production; production calls will fail closed.",
                exc,
            )
            _model = None
    return _model


_token_re = re.compile(r"[a-z0-9#]+")


def _hash_embedding(text: str) -> list[float]:
    """Deterministic 512-dim feature-hash embedding with unigrams+bigrams."""
    vec = [0.0] * EMBEDDING_DIM
    tokens = _token_re.findall(text.lower())
    grams = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
    for gram in grams:
        digest = hashlib.sha256(gram.encode()).digest()
        idx = int.from_bytes(digest[:4], "big") % EMBEDDING_DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _production_backend_error(reason: str) -> EmbeddingBackendError:
    return EmbeddingBackendError(
        f"Production requires real CLIP embeddings (EMBEDDING_BACKEND=clip with "
        f"the model loadable); refusing to continue. Reason: {reason}. "
        f"Hash vectors are a development/test-only backend — see "
        f"docs/ai/model-versions.md. This failure is deliberate: silent hash "
        f"fallback in production corrupts semantic ranking without any signal."
    )


def reset_backend_resolution() -> None:
    """Forget the resolved backend (tests / `--real-embeddings` seeding)."""
    global _backend
    _backend = None


def get_backend() -> str:
    """Resolve the active backend, honoring config and availability.

    Production fails closed: any path that would resolve to ``hash`` raises
    :class:`EmbeddingBackendError` instead of silently downgrading.
    """
    global _backend
    if _backend is not None:
        return _backend
    if settings.EMBEDDING_BACKEND == "clip":
        if _load_clip() is not None:
            _backend = "clip"
            return _backend
        if settings.is_production:
            raise _production_backend_error("CLIP model could not be loaded")
        _backend = "hash"
        return _backend
    # EMBEDDING_BACKEND == "hash"
    if settings.is_production:
        raise _production_backend_error(
            "EMBEDDING_BACKEND=hash is configured; hash is not a production backend"
        )
    _backend = "hash"
    return _backend


def validate_embedding_runtime() -> dict:
    """Eager startup check + info dict (called from ``app.main`` lifespan).

    Raises :class:`EmbeddingBackendError` under the same production rules as
    :func:`get_backend`; returns the backend identity for logging/metrics.

    Stage 04 remediation (IR-AI-001 wiring): beyond backend resolution, a
    probe embedding is verified for dimension, finiteness and unit norm, so a
    mis-built or mismatched model (wrong output dim, bad normalization) fails
    startup instead of corrupting the ``vector(512)`` column on first write.
    """
    backend = get_backend()
    probe = get_embedding("startup validation probe")
    problems = verify_embedding(probe)
    if problems:
        raise EmbeddingBackendError(
            f"Embedding runtime failed its startup self-check: "
            f"{'; '.join(problems)}. Backend {backend!r} does not produce valid "
            f"{EMBEDDING_DIM}-dim unit vectors; refusing to serve — see "
            f"docs/ai/model-versions.md (re-embedding runbook)."
        )
    return {
        "backend": backend,
        "model": EMBEDDING_MODEL_BACKENDS[backend],
        "dim": EMBEDDING_DIM,
        "production": settings.is_production,
        "self_check": "passed",
    }


def verify_embedding(vec: list[float] | None) -> list[str]:
    """Return a list of problems with ``vec`` (empty list = a valid vector).

    Checks dimension, NaN/inf values and L2 normalization. Used by tests,
    seeders and the evaluation harness to catch a wrong-dimension or
    unnormalized model before it reaches the pgvector column.
    """
    if vec is None:
        return ["embedding is None"]
    problems: list[str] = []
    if len(vec) != EMBEDDING_DIM:
        problems.append(f"dimension {len(vec)} != configured {EMBEDDING_DIM}")
        return problems
    if any(not math.isfinite(x) for x in vec):
        problems.append("contains NaN or infinity")
        return problems
    norm = math.sqrt(sum(x * x for x in vec))
    if abs(norm - 1.0) > NORM_TOLERANCE:
        problems.append(f"not L2-normalized (norm={norm:.6f})")
    return problems


def get_embedding(text: str, image_path: Optional[str] = None) -> list[float]:
    """Embed ``text`` (and optionally an image) into a 512-dim vector.

    When an image path is given and CLIP is active, the result is the
    L2-normalized mean of the text and image embeddings (multimodal query).
    """
    backend = get_backend()
    if backend == "clip":
        model = _load_clip()
        inputs: list = [text]
        if image_path:
            try:
                from PIL import Image

                inputs.append(Image.open(image_path))
            except Exception as exc:
                logger.warning("image %s unreadable (%s); text-only", image_path, exc)
        embs = model.encode(inputs, normalize_embeddings=True)
        if len(embs) == 1:
            return embs[0].tolist()
        mean = (embs[0] + embs[1]) / 2.0
        norm = float((mean @ mean) ** 0.5) or 1.0
        return (mean / norm).tolist()
    return _hash_embedding(text)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors, safe for zero vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def quiz_to_text(styles: list[str], colors: list[str], materials: list[str],
                 patterns: list[str] | None = None) -> str:
    """Canonical text serialization of quiz answers for embedding."""
    parts = []
    if styles:
        parts.append(" ".join(styles) + " style living room furniture")
    if materials:
        parts.append("made of " + " and ".join(materials))
    if colors:
        parts.append("colors " + " ".join(colors))
    if patterns:
        parts.append("patterns " + " ".join(patterns))
    return ", ".join(parts) or "living room furniture"


def product_to_text(title: str, styles: list[str], colors: list[str],
                    materials: list[str], description: str = "",
                    patterns: list[str] | None = None) -> str:
    """Canonical text serialization of a product for embedding."""
    parts = [title]
    if styles:
        parts.append(" ".join(styles) + " style")
    if materials:
        parts.append("made of " + " and ".join(materials))
    if colors:
        parts.append("colors " + " ".join(colors))
    if patterns:
        parts.append("patterns " + " ".join(patterns))
    if description:
        parts.append(description)
    return ", ".join(parts)


if __name__ == "__main__":  # python -m ai.embedding_service
    import time

    t0 = time.time()
    vec = get_embedding("a modern walnut coffee table with black metal legs")
    dt = time.time() - t0
    print(f"backend={get_backend()} dim={len(vec)} load+embed={dt:.2f}s")
    problems = verify_embedding(vec)
    print(f"verify={problems or 'OK'}")
    assert len(vec) == EMBEDDING_DIM
    assert not problems, f"embedding failed verification: {problems}"
    assert dt < 10, "model must load in <10s"
    print("OK")
