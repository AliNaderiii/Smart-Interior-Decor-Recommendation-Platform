"""Provider-agnostic AI feature extraction from furniture images.

``FeatureExtractor.extract(image_url)`` returns::

    {
      "colors": ["#A0522D", ...],
      "style": ["modern", ...],
      "material": ["wood", ...],
      "patterns": ["solid", ...],
      "description_for_embedding": "a modern walnut coffee table ...",
      "confidence": 0.87,
    }

Providers are selected via ``settings.AI_PROVIDER``:
  * ``gemini`` — Google gemini-2.0-flash (REST, key from GEMINI_API_KEY)
  * ``openai`` — gpt-4o-mini vision (REST, key from OPENAI_API_KEY)
  * ``mock``   — deterministic heuristic extractor (offline dev / CI / tests)

The prompt forces JSON-only output; responses are hardened against
markdown fences and trailing text.
"""
from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

ALLOWED_STYLES = ["modern", "scandinavian", "industrial", "boho", "minimal", "classic"]
ALLOWED_MATERIALS = ["wood", "metal", "fabric", "leather", "glass", "rattan"]
ALLOWED_PATTERNS = ["solid", "geometric", "floral", "striped", "abstract", "persian"]

EXTRACTION_PROMPT = (
    "Analyze this furniture image. Return ONLY valid JSON, no markdown, no prose: "
    '{"colors": ["#HEX"], '
    f'"style": {json.dumps(ALLOWED_STYLES)} (pick 1-2 that apply), '
    f'"material": {json.dumps(ALLOWED_MATERIALS)} (pick all that apply), '
    f'"patterns": {json.dumps(ALLOWED_PATTERNS)} (pick 1), '
    '"description_for_embedding": "a modern walnut coffee table with black metal legs", '
    '"confidence": 0.0-1.0}'
)

_json_re = re.compile(r"\{.*\}", re.DOTALL)


def _parse_json_strict(raw: str) -> dict[str, Any]:
    """Parse model output into JSON, stripping markdown fences if present."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL)
    match = _json_re.search(raw)
    if not match:
        raise ValueError(f"no JSON object in model output: {raw[:200]}")
    return json.loads(match.group(0))


def _sanitize(data: dict[str, Any]) -> dict[str, Any]:
    """Clamp model output to the allowed taxonomy."""
    styles = [s for s in data.get("style", []) if s in ALLOWED_STYLES]
    materials = [m for m in data.get("material", []) if m in ALLOWED_MATERIALS]
    patterns = [p for p in data.get("patterns", []) if p in ALLOWED_PATTERNS]
    colors = [
        c for c in data.get("colors", [])
        if isinstance(c, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", c)
    ]
    conf = float(data.get("confidence", 0.5))
    return {
        "colors": colors[:4],
        "style": styles[:2],
        "material": materials[:3],
        "patterns": patterns[:1],
        "description_for_embedding": str(data.get("description_for_embedding", ""))[:500],
        "confidence": max(0.0, min(1.0, conf)),
    }


class BaseProvider(ABC):
    @abstractmethod
    def extract(self, image_url: str) -> dict[str, Any]: ...


class GeminiProvider(BaseProvider):
    """gemini-2.0-flash via the Generative Language REST API."""

    def extract(self, image_url: str) -> dict[str, Any]:
        img = httpx.get(image_url, timeout=30, follow_redirects=True)
        img.raise_for_status()
        import base64

        b64 = base64.b64encode(img.content).decode()
        mime = img.headers.get("content-type", "image/jpeg").split(";")[0]
        resp = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.GEMINI_MODEL}:generateContent",
            params={"key": settings.GEMINI_API_KEY},
            json={
                "contents": [{
                    "parts": [
                        {"text": EXTRACTION_PROMPT},
                        {"inline_data": {"mime_type": mime, "data": b64}},
                    ]
                }],
                "generationConfig": {"response_mime_type": "application/json"},
            },
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return _sanitize(_parse_json_strict(text))


class OpenAIProvider(BaseProvider):
    """gpt-4o-mini vision via the Chat Completions REST API."""

    def extract(self, image_url: str) -> dict[str, Any]:
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
            json={
                "model": settings.OPENAI_MODEL,
                "response_format": {"type": "json_object"},
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": EXTRACTION_PROMPT},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }],
            },
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        return _sanitize(_parse_json_strict(text))


class MockProvider(BaseProvider):
    """Deterministic heuristic extractor for offline dev / CI.

    Infers tags from keywords in the image URL/filename — good enough to
    exercise the full pipeline and the benchmark harness end-to-end.
    """

    _style_hints = {
        "modern": "modern", "scandi": "scandinavian", "nordic": "scandinavian",
        "industrial": "industrial", "loft": "industrial", "boho": "boho",
        "bohemian": "boho", "minimal": "minimal", "classic": "classic",
        "vintage": "classic",
    }
    _material_hints = {
        "wood": "wood", "walnut": "wood", "oak": "wood", "teak": "wood",
        "metal": "metal", "steel": "metal", "iron": "metal",
        "fabric": "fabric", "linen": "fabric", "velvet": "fabric",
        "leather": "leather", "glass": "glass", "rattan": "rattan",
        "wicker": "rattan",
    }
    _color_hints = {
        "walnut": "#5D4037", "oak": "#C8A165", "black": "#1A1A1A",
        "white": "#F5F5F5", "gray": "#9E9E9E", "grey": "#9E9E9E",
        "green": "#4C6444", "blue": "#3B5B7A", "beige": "#D9CBB3",
        "brown": "#6D4C33", "terracotta": "#C1633F", "cream": "#F2E8D5",
    }

    def extract(self, image_url: str) -> dict[str, Any]:
        low = image_url.lower()
        styles = sorted({v for k, v in self._style_hints.items() if k in low})
        materials = sorted({v for k, v in self._material_hints.items() if k in low})
        colors = [v for k, v in self._color_hints.items() if k in low]
        return _sanitize({
            "colors": colors or ["#D9CBB3"],
            "style": styles or ["modern"],
            "material": materials or ["wood"],
            "patterns": ["solid"],
            "description_for_embedding": (
                f"a {' '.join(styles or ['modern'])} living room piece made of "
                f"{' and '.join(materials or ['wood'])}"
            ),
            "confidence": 0.9 if (styles and materials) else 0.6,
        })


class FeatureExtractor:
    """Facade — picks the provider from settings, with graceful fallback."""

    def __init__(self, provider: str | None = None) -> None:
        name = provider or settings.AI_PROVIDER
        if name == "gemini" and settings.GEMINI_API_KEY:
            self.provider: BaseProvider = GeminiProvider()
        elif name == "openai" and settings.OPENAI_API_KEY:
            self.provider = OpenAIProvider()
        else:
            if name not in ("mock",):
                logger.warning("AI provider %r has no API key; using mock", name)
            self.provider = MockProvider()

    def extract(self, image_url: str) -> dict[str, Any]:
        """Extract features; on provider failure fall back to mock so the
        admin pipeline never hard-crashes (result flagged low confidence)."""
        try:
            return self.provider.extract(image_url)
        except Exception as exc:
            logger.error("extraction failed via %s: %s", type(self.provider).__name__, exc)
            result = MockProvider().extract(image_url)
            result["confidence"] = min(result["confidence"], 0.3)
            return result
