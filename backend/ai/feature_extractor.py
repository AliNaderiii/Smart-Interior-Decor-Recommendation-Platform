"""Provider-agnostic AI feature extraction from furniture images.

``FeatureExtractor.extract(image_url)`` returns::

    {
      "colors": ["#A0522D", ...],
      "style": ["modern", ...],
      "material": ["wood", ...],
      "patterns": ["solid", ...],
      "description_for_embedding": "a modern walnut coffee table ...",
      "confidence": 0.87,
      "provider": "gemini",                  # which provider produced this
      "model": "gemini-3.5-flash",
      "prompt_version": "p2",                # ai.model_registry stamp
      "taxonomy_version": "2.1",
      "needs_review": False,                 # ai.extraction_review gate
      "review_reasons": [],
    }

Providers are selected via ``settings.AI_PROVIDER``:
  * ``gemini`` — Google Gemini vision (REST, key from GEMINI_API_KEY)
  * ``openai`` — gpt-4o-mini vision (REST, key from OPENAI_API_KEY)
  * ``mock``   — deterministic heuristic extractor (offline dev / CI / tests)

Stage 04 hardening (Master Prompt 04):

* **SSRF guard (closes IR-SEC-003 / risk D-03):** the Gemini provider
  downloads the image server-side; every fetch (and every redirect hop) is now
  validated by ``app.core.url_safety.validate_public_url(resolve=True)`` —
  the same defence the seller-link checker already had.
* **Version stamping:** provider, model, prompt version and taxonomy version
  travel with the result (``ai.model_registry``).
* **Review gate:** ``needs_review``/``review_reasons`` computed by
  ``ai.extraction_review.review_decision``; the upload flow stores them in
  ``extraction_raw``.
* **No fabricated fallback in production:** if the provider fails, production
  gets an *empty*, flagged result for human review — never keyword-guessed
  features that look real. Outside production the deterministic keyword
  fallback is kept for developer convenience but is explicitly labelled
  ``provider="mock-fallback"`` and confidence-capped at 0.3 so it can never
  pass the review gate.

The prompt forces JSON-only output; responses are hardened against markdown
fences and trailing text.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx

from ai import taxonomy as tax
from ai.extraction_review import FALLBACK_CONFIDENCE_CAP, review_decision
from ai.model_registry import EXTRACTION_PROMPT_VERSION
from app.core.config import ai_provider_problems, settings
from app.core.url_safety import UnsafeUrl, validate_public_url

logger = logging.getLogger(__name__)

#: Cap for on-disk benchmark images (the harness resizes to ~768 px anyway).
_MAX_LOCAL_IMAGE_BYTES = 10 * 1024 * 1024

#: Backoff pacing for transient Gemini failures (429 rate limit / 5xx blips /
#: transport-level resets — SSL EOF, aborted connections on VPN tunnels).
#: ``GEMINI_MAX_ATTEMPTS`` (env) overrides the attempt budget; default 5.
_GEMINI_RETRY_BASE_SECONDS = 10.0
_GEMINI_RETRY_CAP_SECONDS = 65.0


def _gemini_retry_wait(retry_after: str | None, attempt: int) -> float:
    """Seconds to wait before retrying a transiently-failed Gemini call.

    Honours the ``Retry-After`` header when Google sends one; otherwise
    exponential backoff (10s, 20s, 40s, … capped) — long enough for a
    per-minute free-tier quota window to slide past, short enough for the
    offline benchmark run to terminate.
    """
    if retry_after:
        try:
            return min(_GEMINI_RETRY_CAP_SECONDS, max(1.0, float(retry_after)))
        except ValueError:
            pass  # HTTP-date form — fall through to exponential backoff
    return min(_GEMINI_RETRY_CAP_SECONDS, _GEMINI_RETRY_BASE_SECONDS * 2 ** (attempt - 1))

#: MIME lookup for local benchmark images.
_MIME_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


class ProviderConfigurationError(RuntimeError):
    """The selected AI provider cannot run in this environment (fail-closed).

    Raised in production when ``AI_PROVIDER``/its API key are misconfigured.
    The message names the exact settings to fix and never contains key values.
    """

ALLOWED_STYLES = tax.styles()
ALLOWED_MATERIALS = tax.materials()
ALLOWED_PATTERNS = tax.patterns()

EXTRACTION_PROMPT = (
    # p5 (2026-09-01): full-50 real runs with p4 landed at 79.2%
    # (gemini-3.5-flash-lite) / 80.0% (gemini-3.6-flash sample). Residual
    # failure signature: 14/50 style misses at the 2-slot hedge and phantom
    # minority materials ("wood" legs on a fabric sofa). p5 widens the style
    # hedge to up-to-3 (free under the overlap-based contract term, gated by
    # human review downstream), tightens "material" to co-dominance, and
    # states JSON types explicitly after a scalar-not-list patterns answer
    # ("geometric") shredded into characters downstream.
    "Analyze this furniture image. Return ONLY valid JSON, no markdown, no prose. "
    'Every field is a JSON ARRAY except confidence: {"colors": ["#HEX"], '
    '"style": ["...", "..."], "material": ["..."], "patterns": ["..."], '
    '"description_for_embedding": "...", "confidence": 0.0-1.0}. '
    "Rules: "
    f'"style": up to 3 entries from {json.dumps(ALLOWED_STYLES)}, best match first. '
    "NEVER output a word outside that list — translate FIRST: minimalist->minimal, "
    "scandi/nordic->scandinavian, contemporary/mid-century->modern, "
    "traditional->classic, rustic/eclectic/coastal->boho, loft/urban->industrial. "
    f'"material": from {json.dumps(ALLOWED_MATERIALS)} — only what is clearly VISIBLE '
    "and structurally dominant. A fabric sofa's wood legs are NOT co-dominant: one "
    "entry. Wood frame + fabric seat IS co-dominant: two entries. Never more than 2. "
    f'"patterns": exactly ONE entry as an array (e.g. ["geometric"]), from '
    f'{json.dumps(ALLOWED_PATTERNS)} ("solid" when plain). '
    '"colors": 1-3 dominant hex colors. '
    '"confidence": honest 0.0-1.0 (0.5 = guessing).'
)

_json_re = re.compile(r"\{.*\}", re.DOTALL)
_hex_re = re.compile(r"#[0-9A-Fa-f]{6}")


def _parse_json_strict(raw: str) -> dict[str, Any]:
    """Parse model output into JSON, stripping markdown fences if present."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL)
    match = _json_re.search(raw)
    if not match:
        raise ValueError(f"no JSON object in model output: {raw[:200]}")
    return json.loads(match.group(0))


def _as_str_list(value: Any) -> list:
    """Tolerate scalar fields where a list was asked for.

    Observed live on gemini-3.5-flash-lite (real run, image id 2): the model
    answered ``"patterns": "geometric"`` (a bare string). Iterating that
    string shredded it into single characters, which the taxonomy clamp then
    flagged as unknown values (["c","e","g", ...]) and bounced the item to
    human review. Wrap scalars into a one-item list; pass lists through.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _sanitize(data: dict[str, Any]) -> dict[str, Any]:
    """Clamp model output to the allowed taxonomy — never guess.

    Unknown taxonomy values are dropped and reported in
    ``unknown_taxonomy_values`` (which forces human review) rather than being
    mapped to a "closest" value: a hallucinated style is worse for
    recommendations than a missing one, because a missing one is visible.
    """
    raw_styles = [s for s in _as_str_list(data.get("style")) if isinstance(s, str)]
    raw_materials = [m for m in _as_str_list(data.get("material")) if isinstance(m, str)]
    raw_patterns = [p for p in _as_str_list(data.get("patterns")) if isinstance(p, str)]
    styles, unknown_s = tax.clamp_to_taxonomy(raw_styles, "style")
    materials, unknown_m = tax.clamp_to_taxonomy(raw_materials, "material")
    patterns, unknown_p = tax.clamp_to_taxonomy(raw_patterns, "pattern")
    unknown = sorted(set(unknown_s + unknown_m + unknown_p))

    colors = [
        c for c in data.get("colors", [])
        if isinstance(c, str) and re.fullmatch(_hex_re, c)
    ]
    try:
        conf = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        conf = 0.0
    return {
        "colors": colors[:4],
        "style": styles[:2],
        "material": materials[:3],
        "patterns": patterns[:1],
        "description_for_embedding": str(data.get("description_for_embedding", ""))[:500],
        "confidence": max(0.0, min(1.0, conf)),
        "unknown_taxonomy_values": unknown,
    }


class BaseProvider(ABC):
    #: short name stamped into results and evidence
    name = "base"

    @abstractmethod
    def extract(self, image_url: str) -> dict[str, Any]: ...


def _fetch_image_bytes(url: str, timeout: float = 30.0) -> tuple[bytes, str]:
    """Read image bytes for the vision model.

    Two input kinds, strictly separated:

    * **Local files** — an existing on-disk path (the offline benchmark
      harness passes these via ``--images-dir``). Read directly; no URL
      parsing, no network. Size-capped; MIME from the extension.
    * **Remote http(s) URLs** — downloaded with SSRF guarding on every hop:

    The pre-Stage-04 code called ``httpx.get(url, follow_redirects=True)``:
    a public URL that 302s to ``http://169.254.169.254/...`` turned the
    extractor into a cloud-metadata exfiltration primitive, exactly like the
    seller-link checker before T-35. Same fix, same pattern: manual redirect
    following with per-hop validation.
    """
    if not url.startswith(("http://", "https://")):
        p = Path(url)
        if p.is_file():
            size = p.stat().st_size
            if size > _MAX_LOCAL_IMAGE_BYTES:
                raise UnsafeUrl(
                    f"local image too large ({size} bytes > {_MAX_LOCAL_IMAGE_BYTES})"
                )
            mime = _MIME_BY_EXT.get(p.suffix.lower())
            if mime is None:
                raise UnsafeUrl(f"unsupported local image extension: {p.suffix!r}")
            return p.read_bytes(), mime
        # fall through to URL validation for a precise, fielded error
    target = validate_public_url(url, resolve=True, field="image_url")
    with httpx.Client(follow_redirects=False, timeout=timeout) as client:
        for _ in range(5):
            resp = client.get(target)
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("location", "")
                if not location:
                    raise UnsafeUrl("redirect without location")
                nxt = str(httpx.URL(target).join(location))
                target = validate_public_url(nxt, resolve=True, field="image_url redirect")
                continue
            resp.raise_for_status()
            mime = resp.headers.get("content-type", "image/jpeg").split(";")[0]
            return resp.content, mime
    raise UnsafeUrl("too many redirects fetching image")


class GeminiProvider(BaseProvider):
    """Gemini vision via the Generative Language REST API."""

    name = "gemini"

    def extract(self, image_url: str) -> dict[str, Any]:
        data, mime = _fetch_image_bytes(image_url)
        b64 = base64.b64encode(data).decode()
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.GEMINI_MODEL}:generateContent"
        )
        payload = {
            "contents": [{
                "parts": [
                    {"text": EXTRACTION_PROMPT},
                    {"inline_data": {"mime_type": mime, "data": b64}},
                ]
            }],
            "generationConfig": {"response_mime_type": "application/json"},
        }
        # Transient failures must be retried, not silently degraded to the
        # mock fallback: 429 (free-tier per-minute quota), 5xx (Google-side
        # blips) and httpx.TransportError (SSL EOF / connection resets on
        # flaky VPN tunnels). Other 4xx are configuration errors — fail fast.
        max_attempts = max(1, int(os.getenv("GEMINI_MAX_ATTEMPTS", "5")))
        resp: httpx.Response | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp = httpx.post(
                    url,
                    params={"key": settings.GEMINI_API_KEY},
                    json=payload,
                    timeout=60,
                )
                resp.raise_for_status()
                break
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                if (code != 429 and code < 500) or attempt == max_attempts:
                    raise
                wait = _gemini_retry_wait(exc.response.headers.get("retry-after"), attempt)
            except httpx.TransportError:
                if attempt == max_attempts:
                    raise
                wait = _gemini_retry_wait(None, attempt)
            logger.warning(
                "Gemini attempt %d/%d failed transiently; retrying in %.0fs",
                attempt, max_attempts, wait,
            )
            time.sleep(wait)
        assert resp is not None  # loop either breaks with a response or raises
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return _sanitize(_parse_json_strict(text))


class OpenAIProvider(BaseProvider):
    """gpt-4o-mini vision via the Chat Completions REST API.

    Works with any OpenAI-compatible endpoint: set ``OPENAI_BASE_URL`` to
    point at a gateway (e.g. a regional aggregator) instead of
    ``api.openai.com``. Auth stays ``Authorization: Bearer <OPENAI_API_KEY>``.

    Remote http(s) image URLs are handed to the provider (their fetchers
    download it), so the SSRF risk profile differs: the scheme/private-host
    check still runs to keep stored URLs sane, but resolution is not ours
    to enforce. Local files (the offline benchmark's ``--images-dir``) are
    read by ``_fetch_image_bytes`` and inlined as data URLs.
    """

    name = "openai"

    def extract(self, image_url: str) -> dict[str, Any]:
        if image_url.startswith(("http://", "https://")):
            validate_public_url(image_url, resolve=False, field="image_url")
            img_url = image_url
        else:
            data, mime = _fetch_image_bytes(image_url)
            img_url = f"data:{mime};base64,{base64.b64encode(data).decode()}"
        base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        payload = {
            "model": settings.OPENAI_MODEL,
            "response_format": {"type": "json_object"},
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": EXTRACTION_PROMPT},
                    {"type": "image_url", "image_url": {"url": img_url}},
                ],
            }],
        }
        # Same transient-failure policy as Gemini: 429 (gateway/provider
        # rate limit), 5xx and transport resets are retried with backoff;
        # other 4xx remain fail-fast configuration errors. Attempt budget
        # via ``OPENAI_MAX_ATTEMPTS`` (default 5).
        max_attempts = max(1, int(os.getenv("OPENAI_MAX_ATTEMPTS", "5")))
        resp: httpx.Response | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp = httpx.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    json=payload,
                    timeout=60,
                )
                resp.raise_for_status()
                break
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                if (code != 429 and code < 500) or attempt == max_attempts:
                    raise
                wait = _gemini_retry_wait(exc.response.headers.get("retry-after"), attempt)
            except httpx.TransportError:
                if attempt == max_attempts:
                    raise
                wait = _gemini_retry_wait(None, attempt)
            logger.warning(
                "OpenAI attempt %d/%d failed transiently; retrying in %.0fs",
                attempt, max_attempts, wait,
            )
            time.sleep(wait)
        assert resp is not None  # loop either breaks with a response or raises
        text = resp.json()["choices"][0]["message"]["content"]
        return _sanitize(_parse_json_strict(text))


class MockProvider(BaseProvider):
    """Deterministic heuristic extractor for offline dev / CI.

    Infers tags from keywords in the image URL/filename — good enough to
    exercise the full pipeline and the benchmark harness end-to-end. **It never
    looks at pixels**, so any score produced with it is a harness baseline, not
    a vision-model accuracy claim (every result is stamped provider=mock and
    the benchmark reports it as MOCK).
    """

    name = "mock"

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


def _empty_failed_extraction(image_url: str, error: Exception) -> dict[str, Any]:
    """Production failure result: no features, honest error, forced review."""
    return {
        "colors": [],
        "style": [],
        "material": [],
        "patterns": [],
        "description_for_embedding": "",
        "confidence": 0.0,
        "unknown_taxonomy_values": [],
        "provider": "failed",
        "provider_error": f"{type(error).__name__}: {str(error)[:300]}",
        "image_url": image_url,
        "needs_review": True,
        "review_reasons": ["provider_error", "low_confidence", "missing_style", "missing_material"],
    }


def _labelled_fallback(
    result: dict[str, Any],
    *,
    error: Exception | None = None,
    config_problem: str | None = None,
) -> dict[str, Any]:
    """Stamp a mock-derived result so it can never masquerade as model output.

    Applied whenever the values did **not** come from the selected real
    provider — provider construction failed on configuration, or the provider
    raised at request time. Label ``provider="mock-fallback"`` + confidence
    capped at ``FALLBACK_CONFIDENCE_CAP`` keeps the review gate rejecting it
    in every environment.
    """
    result["provider"] = "mock-fallback"
    result["model"] = "filename-heuristic (fallback)"
    if error is not None:
        result["provider_error"] = f"{type(error).__name__}: {str(error)[:300]}"
    if config_problem:
        result["provider_config_error"] = config_problem[:300]
    conf = float(result.get("confidence", 0.0) or 0.0)
    result["confidence"] = min(conf, FALLBACK_CONFIDENCE_CAP)
    return result


class FeatureExtractor:
    """Facade — picks the provider from settings, fail-closed in production.

    Stage 04 remediation: the previous constructor silently substituted
    ``MockProvider`` whenever the selected provider's key was missing —
    including in production, where the keyword heuristic's 0.9 confidence
    could pass the review gate. Selection now goes through the single
    authoritative rule in ``app.core.config.ai_provider_problems`` (the same
    one ``Settings.validate_runtime`` enforces at startup):

    * production + ``AI_PROVIDER=mock``                       → error
    * production + ``gemini``/``openai`` without *its* key    → error
      (a key for the other provider is not accepted)
    * development/test with a misconfigured real provider     → the
      deterministic fallback stays usable, but every result is labelled
      ``provider="mock-fallback"`` and confidence-capped at 0.30
    """

    def __init__(self, provider: str | None = None) -> None:
        name = provider or settings.AI_PROVIDER
        problems = ai_provider_problems(
            name,
            has_gemini_key=bool(settings.GEMINI_API_KEY),
            has_openai_key=bool(settings.OPENAI_API_KEY),
            production=settings.is_production,
        )
        self._fallback_problem: str | None = None
        if problems:
            if settings.is_production:
                raise ProviderConfigurationError("; ".join(problems))
            # Dev/test: keep the pipeline usable, but visibly degraded.
            self._fallback_problem = "; ".join(problems)
            logger.warning(
                "AI provider misconfigured (%s); using labelled mock-fallback",
                self._fallback_problem,
            )
            self.provider: BaseProvider = MockProvider()
        elif name == "gemini":
            self.provider = GeminiProvider()
        elif name == "openai":
            self.provider = OpenAIProvider()
        else:
            self.provider = MockProvider()

    def extract(self, image_url: str) -> dict[str, Any]:
        """Extract features; on provider failure return a flagged result.

        In production the failure result is empty (nothing fabricated);
        elsewhere the deterministic keyword fallback keeps the dev pipeline
        usable but is labelled ``mock-fallback`` and capped at 0.3 confidence
        so the review gate always rejects it.
        """
        try:
            result = self.provider.extract(image_url)
        except Exception as exc:
            logger.error(
                "extraction failed via %s: %s", type(self.provider).__name__, exc
            )
            if settings.is_production:
                result = _empty_failed_extraction(image_url, exc)
            else:
                result = _labelled_fallback(
                    MockProvider().extract(image_url), error=exc
                )
        else:
            if self._fallback_problem is not None:
                result = _labelled_fallback(result, config_problem=self._fallback_problem)
            else:
                result.setdefault("provider", self.provider.name)
                result.setdefault("model", _provider_model(self.provider.name))
            result.setdefault("prompt_version", EXTRACTION_PROMPT_VERSION)
            result.setdefault("taxonomy_version", tax.taxonomy_version())
            result.setdefault("image_url", image_url)

        # Defence in depth (Stage 04 remediation): a mock-derived payload must
        # never leave this method unflagged in production, whatever path got
        # us here. Unreachable by construction; cheap to guarantee.
        if settings.is_production and result.get("provider") in ("mock", "mock-fallback"):
            result = _empty_failed_extraction(
                image_url,
                RuntimeError(
                    f"mock provider output reached production extraction "
                    f"(provider={result.get('provider')!r})"
                ),
            )

        decision = review_decision(result)
        result["needs_review"] = decision["needs_review"]
        result["review_reasons"] = decision["review_reasons"]
        return result


def _provider_model(name: str) -> str:
    return {
        "gemini": settings.GEMINI_MODEL,
        "openai": settings.OPENAI_MODEL,
        "mock": "filename-heuristic",
    }.get(name, name)
