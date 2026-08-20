"""SQLAlchemy 2.0 sync engine/session.

Decision (ADR-004): synchronous SQLAlchemy with FastAPI's threadpool.
Simpler transactional semantics, plays perfectly with Alembic, and the
recommendation hot path is CPU/pgvector-bound, not IO-bound.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# Pool sized for the 100-concurrent /recommend acceptance test:
# 2 uvicorn workers x (20 + 30 overflow) covers burst traffic while staying
# well under Postgres' default max_connections=100.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=30,
    pool_timeout=30,
    connect_args=connect_args,
)

if settings.DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_fk(dbapi_conn, _record):  # pragma: no cover
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
