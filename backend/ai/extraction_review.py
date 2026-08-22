"""Extraction confidence thresholds and human-review gate.

Master Prompt 04 work item 6: "Enforce human review for low-confidence/failed
extraction". The gate itself lives here so the extractor, the (requested) admin
review queue and the evaluation harness all apply **the same** rule instead of
each re-implementing a threshold.

Policy (v2026-08-21.1):

* ``confidence >= AUTO_ACCEPT_THRESHOLD`` (0.80) **and** no failure markers →
  ``auto_accept``: eligible for the normal verification flow (an admin still
  signs off `is_verified`, but the extraction is not pre-flagged).
* Anything else → ``human_review`` with machine-readable reasons.

Failure markers that force review regardless of confidence:

* ``provider_error`` — the vision provider failed and (outside production) the
  keyword fallback produced the values;
* ``unknown_taxonomy_values`` — the model returned values outside the taxonomy;
  they were discarded, not guessed;
* empty required feature lists (style or material) — nothing to recommend on.

The contracted quality bar is 80% on the 50-image benchmark
(docs/ARCHITECTURE.md §Benchmarks); the auto-accept threshold mirrors it so a
product only skips pre-flagged review when the extractor is at least as
confident as the bar the platform publicly claims.
"""
from __future__ import annotations

from typing import Any

#: Confidence at/above which an extraction may skip the pre-flagged review path.
AUTO_ACCEPT_THRESHOLD = 0.80
#: Confidence at/above which an extraction is at least *eligible* for
#: auto-accept; between REVIEW_FLOOR and AUTO_ACCEPT it is always reviewed.
REVIEW_FLOOR = 0.60
#: Hard cap applied to any fallback result so it can never reach auto-accept.
FALLBACK_CONFIDENCE_CAP = 0.30

_REASONS = {
    "low_confidence": "confidence below AUTO_ACCEPT_THRESHOLD (0.80)",
    "provider_error": "vision provider failed; values are fallback/empty, not model output",
    "unknown_taxonomy_values": "model returned values outside the taxonomy; they were discarded",
    "missing_style": "no style recognised — recommendations would be blind on the dominant signal",
    "missing_material": "no material recognised",
}


def review_decision(extraction: dict[str, Any]) -> dict[str, Any]:
    """Return ``{"needs_review": bool, "review_reasons": [codes], "state": ...}``.

    Pure function over the extraction payload (the same dict that is stored in
    ``products.extraction_raw``), so stored rows can be re-audited if the
    thresholds ever change.
    """
    reasons: list[str] = []
    conf = float(extraction.get("confidence", 0.0) or 0.0)
    if conf < AUTO_ACCEPT_THRESHOLD:
        reasons.append("low_confidence")
    if extraction.get("provider_error"):
        reasons.append("provider_error")
    if extraction.get("unknown_taxonomy_values"):
        reasons.append("unknown_taxonomy_values")
    if not extraction.get("style"):
        reasons.append("missing_style")
    if not extraction.get("material"):
        reasons.append("missing_material")

    state = "auto_accept" if not reasons else "human_review"
    return {
        "state": state,
        "needs_review": state == "human_review",
        "review_reasons": reasons,
        "thresholds": {
            "auto_accept": AUTO_ACCEPT_THRESHOLD,
            "review_floor": REVIEW_FLOOR,
            "fallback_cap": FALLBACK_CONFIDENCE_CAP,
        },
    }
