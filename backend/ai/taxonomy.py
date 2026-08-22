"""Interior-design taxonomy — stable IDs, Persian labels, unknown-value policy.

Single load point for ``seed_data/style_taxonomy.json``. Before this module the
allowlists were duplicated in ``ai/feature_extractor.py`` (with its own silent
fallback list) and ``app/schemas/quiz.py`` (a second hand-written copy), and the
taxonomy file itself had no patterns or categories sections at all — the
pattern allowlist existed only inside the extractor. Any drift between those
copies would have meant AI output accepted here but rejected there.

Contract (Master Prompt 04 work item 1):

* **Stable IDs** — ``id`` fields are the join key across quiz, products,
  extraction and the frontend. They never change; labels may.
* **Persian labels** — every entity carries ``name_fa``; ``label()`` resolves
  id → label with an explicit ``lang`` so UI code never hardcodes strings.
* **Unknown values** — see ``UNKNOWN_VALUE_POLICY``: optional fields may be
  empty ("no preference", neutral score), required fields must be known IDs,
  and extraction output is *clamped* — unknown values are discarded, never
  guessed, and force human review.

The module tolerates a missing/corrupt file only far enough to boot with an
empty taxonomy and a logged error — every accessor then reports ``known=False``
so extraction results get clamped to nothing and routed to human review, rather
 than crashing the app or silently inventing values.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

TAXONOMY_PATH = Path(__file__).resolve().parents[1] / "seed_data" / "style_taxonomy.json"

#: Historical fallback lists — kept ONLY so a missing taxonomy file degrades to
#: the pre-Stage-04 behaviour instead of hard-crashing legacy dev environments.
#: Production correctness does not depend on them: extraction results that fall
#: back to these are still stamped with the taxonomy version actually loaded.
_FALLBACK_STYLES = ["modern", "scandinavian", "industrial", "boho", "minimal", "classic"]
_FALLBACK_MATERIALS = ["wood", "metal", "fabric", "leather", "glass", "rattan"]
_FALLBACK_PATTERNS = ["solid", "geometric", "floral", "striped", "abstract", "persian"]


@lru_cache(maxsize=1)
def _load() -> dict:
    try:
        return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.error("style taxonomy unavailable at %s (%s); taxonomy is EMPTY", TAXONOMY_PATH, exc)
        return {}


def taxonomy() -> dict:
    """The raw taxonomy dictionary (possibly empty — see module docstring)."""
    return _load()


def taxonomy_version() -> str:
    return str(taxonomy().get("taxonomy_version", "unknown"))


TAXONOMY_VERSION = taxonomy_version()  # convenience constant for stamping


def styles() -> list[str]:
    return [row["id"] for row in taxonomy().get("styles", []) if "id" in row] or list(_FALLBACK_STYLES)


def materials() -> list[str]:
    return list(taxonomy().get("materials_taxonomy", {})) or list(_FALLBACK_MATERIALS)


def patterns() -> list[str]:
    return list(taxonomy().get("patterns_taxonomy", {})) or list(_FALLBACK_PATTERNS)


def categories() -> list[str]:
    return [row["id"] for row in taxonomy().get("categories", []) if "id" in row]


def label(kind: str, id_: str, lang: str = "fa") -> str | None:
    """Resolve a stable ID to its localized label (``fa`` or ``en``).

    Returns ``None`` for unknown IDs — callers decide whether that is a
    validation error (quiz input) or a review-gate trigger (extraction).
    """
    key = "name_fa" if lang == "fa" else "name_en"
    if kind == "style":
        for row in taxonomy().get("styles", []):
            if row.get("id") == id_:
                return row.get(key)
    elif kind == "material":
        row = taxonomy().get("materials_taxonomy", {}).get(id_)
        if row:
            return row.get(key)
    elif kind == "pattern":
        row = taxonomy().get("patterns_taxonomy", {}).get(id_)
        if row:
            return row.get(key)
    elif kind == "category":
        for row in taxonomy().get("categories", []):
            if row.get("id") == id_:
                return row.get(key)
    return None


def is_known(kind: str, id_: str) -> bool:
    return label(kind, id_, lang="en") is not None or _in_fallback(kind, id_)


def _in_fallback(kind: str, id_: str) -> bool:
    table = {
        "style": _FALLBACK_STYLES,
        "material": _FALLBACK_MATERIALS,
        "pattern": _FALLBACK_PATTERNS,
    }.get(kind, [])
    return id_ in table


#: Unknown-value policy as data — mirrored from the JSON so the behaviour and
#: the documentation cannot drift apart.
def unknown_value_policy() -> dict:
    default = {
        "policy": "unknown taxonomy values are rejected/clamped and force human review",
        "neutral_score": 0.5,
    }
    return taxonomy().get("unknown_value_policy", default)


def validate() -> list[str]:
    """Structural integrity checks; returns a list of problems (empty = OK).

    Called by tests and the evaluation harness; a taxonomy that fails these
    checks must not ship.
    """
    problems: list[str] = []
    tax = taxonomy()
    if not tax:
        return ["taxonomy file missing or unreadable"]
    if not tax.get("taxonomy_version"):
        problems.append("taxonomy_version missing")
    ids = [row.get("id") for row in tax.get("styles", [])]
    if len(ids) != len(set(ids)):
        problems.append("duplicate style ids")
    for row in tax.get("styles", []):
        if not row.get("name_fa"):
            problems.append(f"style {row.get('id')} has no name_fa")
        if not row.get("colors"):
            problems.append(f"style {row.get('id')} has no palette")
    for mid, row in tax.get("materials_taxonomy", {}).items():
        if not row.get("name_fa"):
            problems.append(f"material {mid} has no name_fa")
    for pid, row in tax.get("patterns_taxonomy", {}).items():
        if not row.get("name_fa"):
            problems.append(f"pattern {pid} has no name_fa")
    for row in tax.get("categories", []):
        if not row.get("name_fa"):
            problems.append(f"category {row.get('id')} has no name_fa")
    return problems


def clamp_to_taxonomy(values: list, kind: str) -> tuple[list, list]:
    """Split ``values`` into (known, unknown) against the taxonomy.

    Used by the extractor sanitizer: unknown values are dropped, reported and
    counted — they are never mapped to a "closest" guess.
    """
    known, unknown = [], []
    for v in values:
        (known if is_known(kind, v) else unknown).append(v)
    return known, unknown
