"""Server-side HTML sanitisation (OWASP A03 — Injection / stored XSS).

Phase 0B stored `<img src=x onerror=alert(1)><script>alert(2)</script>` in a
moodboard title verbatim (`docs/SECURITY_AUDIT_V2.md` §A03). React escapes
text nodes so it is not exploitable in the SPA today, but the value also
reaches share pages, emails and any future PDF/`dangerouslySetInnerHTML`
render — and AI-extracted product copy (Gemini output, prompt-injectable)
travels the same path.

Policy: user-supplied free text is **plain text**, never markup. We strip
tags rather than escape them so the stored value stays human-readable.
"""
from __future__ import annotations

import html
import re
from typing import Annotated

from pydantic import AfterValidator, StringConstraints

_TAG_RE = re.compile(r"<[^>]*>")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
#: Elements whose *contents* are executable/style payloads, not readable text —
#: drop the whole element so `<script>alert(1)</script>` leaves nothing behind
#: rather than the bare string "alert(1)".
_DANGEROUS_EL_RE = re.compile(
    r"<\s*(script|style|iframe|object|embed|svg|math)\b[^>]*>.*?<\s*/\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_WS_RE = re.compile(r"\s{2,}")


def strip_html(value: str) -> str:
    """Remove markup, decode entities, collapse control chars and whitespace."""
    if not value:
        return value
    # Decode first so `&lt;script&gt;` cannot survive as markup after stripping.
    text = html.unescape(value)
    # Strip repeatedly: `<scr<x>ipt>` collapses to `<script>` after one pass,
    # and a nested/partial element needs a second look.
    for _ in range(3):
        new = _DANGEROUS_EL_RE.sub("", text)
        new = _TAG_RE.sub("", new)
        if new == text:
            break
        text = new
    text = _CTRL_RE.sub("", text)
    return _WS_RE.sub(" ", text).strip()


def _clean(value: str) -> str:
    return strip_html(value)


def SafeText(max_length: int = 255, min_length: int = 0):  # noqa: N802
    """A length-bounded, HTML-stripped string type for Pydantic models."""
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
        AfterValidator(_clean),
    ]
