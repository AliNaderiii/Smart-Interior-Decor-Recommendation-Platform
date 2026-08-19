"""Portable vector column type.

On PostgreSQL this is a real ``pgvector`` ``vector(512)`` column (ADR-003)
so we get ivfflat/hnsw indexes and the ``<=>`` cosine operator.  On SQLite
(unit tests, quick local dev) it degrades to a JSON-encoded list and the
recommender computes cosine similarity in Python — same results, slower,
which is fine for tests.
"""
from __future__ import annotations

import json

from pgvector.sqlalchemy import Vector
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core.config import settings


class JSONVector(TypeDecorator):
    """JSON-in-TEXT vector for non-Postgres dialects."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps([float(x) for x in value])

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return json.loads(value)


def vector_type(dim: int | None = None):
    """Return the right vector column type for the configured database."""
    dim = dim or settings.EMBEDDING_DIM
    if settings.is_postgres:
        return Vector(dim)
    return JSONVector()
