"""Embedding service — CLIP ViT-B/32 with an offline deterministic fallback.

Backends (settings.EMBEDDING_BACKEND):
  * ``clip`` — loads ``clip-ViT-B-32`` via sentence-transformers (512-dim),
    cached in memory after the first call. Supports text and images.
  * ``hash`` — deterministic feature-hash embedding (512-dim). Used when the
    model can't be downloaded (offline/CI) and for unit tests. Same API,
    stable cosine geometry: similar texts share token buckets so similarity
    is still meaningful for our tag-based descriptions.

The fallback is automatic: if CLIP fails to load (no internet, no torch),
we log a warning and switch to hash — the platform keeps working.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
import threading
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_DIM = settings.EMBEDDING_DIM  # 512, matches CLIP ViT-B/32

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
                "CLIP unavailable (%s). Using hash fallback, not real CLIP - "
                "generate embeddings_real.json with --real-embeddings on networked machine",
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


def get_backend() -> str:
    """Resolve the active backend, honoring config and availability."""
    global _backend
    if _backend is not None:
        return _backend
    if settings.EMBEDDING_BACKEND == "clip" and _load_clip() is not None:
        _backend = "clip"
    else:
        _backend = "hash"
    return _backend


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
    assert len(vec) == EMBEDDING_DIM
    assert dt < 10, "model must load in <10s"
    print("OK")
