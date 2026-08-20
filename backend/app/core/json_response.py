"""orjson-backed JSON response (V2 Phase 2, performance).

Why not ``fastapi.responses.ORJSONResponse``?
    FastAPI 0.141 deprecates it — it emits a ``FastAPIDeprecationWarning`` on
    *every* request, because FastAPI can now serialise straight to JSON bytes
    via Pydantic when a route declares a ``response_model``. Our routes return
    plain envelope dicts from ``app.core.envelope.ok()`` with no response
    model, so that fast path never engages and we fall back to Starlette's
    stdlib-``json`` encoder.

    Subclassing Starlette's ``JSONResponse`` gets us orjson without touching
    the deprecated FastAPI symbol.

Why it matters here:
    ``POST /recommend`` is by far the heaviest payload in the API — up to five
    categories x eight products, each carrying a nested score breakdown of
    floats plus an explanation object. orjson serialises that several times
    faster than stdlib json and writes floats without the repr round-trip.
"""
from __future__ import annotations

from typing import Any

import orjson
from starlette.responses import JSONResponse


class ORJSONResponse(JSONResponse):
    """Drop-in ``JSONResponse`` that renders with orjson."""

    media_type = "application/json"

    def render(self, content: Any) -> bytes:
        # OPT_SERIALIZE_NUMPY keeps embedding-derived floats safe if a numpy
        # scalar ever leaks into a score breakdown; default=str mirrors the
        # stdlib encoder's tolerance for UUID/datetime.
        return orjson.dumps(
            content,
            option=orjson.OPT_SERIALIZE_NUMPY,
            default=str,
        )
