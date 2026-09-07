"""Room-photo analysis — "show us your room, we fill in the quiz" (ADR-015).

The five-step style quiz is the platform's biggest funnel leak: every
benchmarked competitor (Havenly's AI beta, IKEA Kreativ, Wayfair Decorify)
opens with *"upload a photo of your room"* instead of a questionnaire. This
service turns one photo into a **pre-filled, editable** quiz — never into a
submitted one. The user stays in control; the photo only saves taps.

Two signal sources, deliberately kept separate so the UI (and the tests) can
tell which one produced what:

``palette`` — pixels
    :func:`accent_colors` (saturated accent pieces, hue-binned) followed by
    :func:`app.services.visual_search.extract_palette` (median-cut dominant
    colours, neutral walls demoted). Deterministic, provider-independent,
    always available. Suggested as the quiz's colour palette **as-is** — a
    room's real colours are exactly what the recommender's ``color_score``
    should be matched against, and the accent goes first because it is the
    colour a decorator builds around.

``vision`` — the configured extraction provider
    :class:`ai.feature_extractor.FeatureExtractor` with a **room prompt**
    (a room is not a product: we ask for the room's overall style, the
    dominant material families already present, and whether the room is
    empty). Output is clamped to the taxonomy by the extractor's own
    sanitiser — unknown values are dropped, never guessed. In development /
    CI the provider is the keyword mock; the response says so
    (``meta.provider``) and the UI shows a "heuristic" badge instead of a
    confidence figure.

Confidence tiers drive how much the UI dares to pre-select:

* ``confident`` (>= AUTO_ACCEPT_THRESHOLD, real provider, no review
  reasons): styles + materials + palette all pre-selected; user lands on
  step 1 with everything filled in.
* ``suggested`` (real provider, below the threshold or with review
  reasons): pre-selected, but the page explains it is a guess.
* ``palette_only`` (mock / fallback / provider failure): only the pixel
  palette is applied; style and material stay for the user to pick.

Nothing is persisted: the photo is analysed in memory and discarded (same
privacy stance as visual search, ADR-013). The room dimensions are *not*
estimated — a single uncalibrated photo cannot yield centimetres honestly,
and the fit score (ADR-012) would then rank on invented numbers.
"""
from __future__ import annotations

import colorsys
import io
import logging
from typing import Any

from PIL import Image

from ai import taxonomy as tax
from ai.extraction_review import AUTO_ACCEPT_THRESHOLD
from ai.feature_extractor import FeatureExtractor
from app.services.visual_search import extract_palette

logger = logging.getLogger(__name__)

#: Quiz store limits (frontend ``quizStore.ts``) — never suggest more than the
#: quiz can hold, otherwise the last suggestions silently vanish.
MAX_STYLES = 3
MAX_COLORS = 5
MAX_MATERIALS = 6

#: Providers whose output is a heuristic, not a look at the pixels.
_HEURISTIC_PROVIDERS = frozenset({"mock", "mock-fallback", "failed"})

CONFIDENCE_TIERS = ("confident", "suggested", "palette_only")

#: Accent detection (see :func:`accent_colors`). A saturated piece has to
#: cover at least this share of the frame to count as a deliberate accent
#: rather than a cushion or a book spine.
ACCENT_MIN_SHARE = 0.01
ACCENT_MIN_SATURATION = 0.45
ACCENT_MIN_VALUE = 0.35
ACCENT_MAX = 2
_ACCENT_HUE_BINS = 24  # 15° bins
_THUMB_EDGE = 128


def analyse_room(image_bytes: bytes, *, image_hint: str = "room.jpg") -> dict[str, Any]:
    """Analyse one validated image and return the quiz-prefill contract.

    ``image_hint`` is only used by the keyword mock provider (it never sees
    pixels) — pass the original filename so local demos behave sensibly.
    """
    palette = _room_palette(image_bytes)
    extraction = _run_vision(image_bytes, image_hint)

    provider = str(extraction.get("provider") or "unknown")
    heuristic = provider in _HEURISTIC_PROVIDERS
    confidence = float(extraction.get("confidence") or 0.0)
    review_reasons = list(extraction.get("review_reasons") or [])

    styles = [s for s in extraction.get("style") or [] if tax.is_known("style", s)][:MAX_STYLES]
    materials = [
        m for m in extraction.get("material") or [] if tax.is_known("material", m)
    ][:MAX_MATERIALS]

    if heuristic or not styles:
        tier = "palette_only"
    elif confidence >= AUTO_ACCEPT_THRESHOLD and not review_reasons:
        tier = "confident"
    else:
        tier = "suggested"

    # Colour: the room's own pixels win. The vision model's colour list is
    # kept as a secondary signal only when the pixel palette is empty (a
    # degenerate image), because models are famously loose about exact hex.
    colors = palette[:MAX_COLORS] or [
        c for c in extraction.get("colors") or [] if isinstance(c, str)
    ][:MAX_COLORS]

    suggestion = {
        "styles": styles if tier != "palette_only" else [],
        "materials": materials if tier != "palette_only" else [],
        "color_palette": colors,
        "patterns": [
            p for p in extraction.get("patterns") or [] if tax.is_known("pattern", p)
        ][:1] if tier != "palette_only" else [],
    }
    return {
        "suggestion": suggestion,
        "labels": {
            "styles": [_label_pair("style", s) for s in suggestion["styles"]],
            "materials": [_label_pair("material", m) for m in suggestion["materials"]],
        },
        "confidence_tier": tier,
        "confidence": round(confidence, 3),
        "palette": palette,
        "description": str(extraction.get("description_for_embedding") or "")[:300],
        "review_reasons": review_reasons,
        "meta": {
            "provider": provider,
            "model": extraction.get("model"),
            "prompt_version": extraction.get("prompt_version"),
            "taxonomy_version": tax.taxonomy_version(),
            "heuristic": heuristic,
            "dimensions_estimated": False,
            "unknown_taxonomy_values": list(extraction.get("unknown_taxonomy_values") or []),
        },
    }


def accent_colors(
    image_bytes: bytes,
    *,
    min_share: float = ACCENT_MIN_SHARE,
    min_saturation: float = ACCENT_MIN_SATURATION,
    min_value: float = ACCENT_MIN_VALUE,
    max_out: int = ACCENT_MAX,
) -> list[str]:
    """Saturated *accent* colours a room's dominant palette swallows.

    Median-cut palette extraction (``visual_search.extract_palette``) is
    share-weighted: in a real room the walls, floor and shadows take every
    slot and the one yellow armchair — 3 % of the pixels, but the colour a
    decorator would build around — merges into the wood tones. Rooms are
    mostly neutral by construction, so for *this* use case the rare
    saturated hue is signal, not noise.

    Pixels above the saturation/brightness floors are binned by hue (15°
    bins); a bin that covers at least ``min_share`` of the frame yields one
    swatch (the bin's mean colour). Neutral rooms and flat images return
    ``[]`` — the function never invents an accent. Deterministic.
    """
    with Image.open(io.BytesIO(image_bytes)) as im:
        im = im.convert("RGB")
        im.thumbnail((_THUMB_EDGE, _THUMB_EDGE))
        width, height = im.size
        pixels = im.load()
    total = float(width * height) or 1.0
    # Per hue bin: pixel count, saturation-weighted RGB sums, weight sum. The
    # saturation weighting keeps a bin's swatch close to its most vivid
    # pixels (the chair) rather than the borderline ones (the oak floor).
    bins: dict[int, list[float]] = {}
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
            if s < min_saturation or v < min_value:
                continue
            acc = bins.setdefault(int(h * _ACCENT_HUE_BINS) % _ACCENT_HUE_BINS, [0, 0.0, 0.0, 0.0, 0.0])
            w = s * s
            acc[0] += 1
            acc[1] += r * w
            acc[2] += g * w
            acc[3] += b * w
            acc[4] += w
    # Merge each bin into its larger neighbour (a real object straddles a
    # 15° boundary) so one armchair yields one swatch, not two.
    merged: dict[int, list[float]] = {}
    for key in sorted(bins, key=lambda k: -bins[k][0]):
        target = key
        for neighbour in ((key - 1) % _ACCENT_HUE_BINS, (key + 1) % _ACCENT_HUE_BINS):
            if neighbour in merged and merged[neighbour][0] >= bins[key][0]:
                target = neighbour
                break
        acc = merged.setdefault(target, [0, 0.0, 0.0, 0.0, 0.0])
        for i, val in enumerate(bins[key]):
            acc[i] += val
    out: list[str] = []
    for count, r, g, b, w in sorted(merged.values(), key=lambda a: (-a[0], a[1:])):
        if count / total < min_share or w <= 0:
            break
        out.append(f"#{int(r / w):02X}{int(g / w):02X}{int(b / w):02X}")
        if len(out) >= max_out:
            break
    return out


def _room_palette(image_bytes: bytes) -> list[str]:
    """Accents first, then the dominant palette, capped to the quiz limit."""
    accents = accent_colors(image_bytes)
    dominant = extract_palette(image_bytes)
    out: list[str] = []
    for hex_ in accents + dominant:
        if hex_ not in out:
            out.append(hex_)
        if len(out) >= MAX_COLORS:
            break
    return out


def _run_vision(image_bytes: bytes, image_hint: str) -> dict[str, Any]:
    """Run the configured provider on in-memory bytes; never raise."""
    try:
        return FeatureExtractor().extract_bytes(
            image_bytes, image_hint=image_hint, prompt_kind="room"
        )
    except Exception as exc:  # noqa: BLE001 — analysis must degrade, not 500
        logger.error("room analysis: vision step failed: %s: %s", type(exc).__name__, exc)
        return {
            "provider": "failed",
            "provider_error": f"{type(exc).__name__}: {str(exc)[:200]}",
            "confidence": 0.0,
            "style": [],
            "material": [],
            "colors": [],
            "patterns": [],
            "review_reasons": ["provider_error"],
        }


def _label_pair(kind: str, id_: str) -> dict[str, str]:
    return {
        "id": id_,
        "fa": tax.label(kind, id_, "fa") or id_,
        "en": tax.label(kind, id_, "en") or id_.replace("_", " ").title(),
    }
