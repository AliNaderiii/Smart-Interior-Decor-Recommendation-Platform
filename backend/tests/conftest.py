"""Shared test fixtures — SQLite + fakeredis, seeded product catalog."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_decor.sqlite3")
os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault("EMBEDDING_BACKEND", "hash")
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("PAYMENT_PROVIDER", "mock")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("APP_ENV", "test")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.redis_client import get_redis  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database():
    """Create schema + seed the 100-product catalog once per session."""
    db_file = Path("test_decor.sqlite3")
    if db_file.exists():
        db_file.unlink()
    Base.metadata.create_all(engine)
    from scripts.seed_products import seed

    seed()
    yield
    engine.dispose()
    if db_file.exists():
        db_file.unlink()


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(autouse=True)
def _clear_cache():
    get_redis().flushall()
    yield


@pytest.fixture()
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_headers(client):
    """Register a fresh homeowner and return Authorization headers."""
    import uuid

    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": "Test User"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    return {"Authorization": f"Bearer {data['access_token']}"}, data


@pytest.fixture()
def admin_headers(client, db):
    """Login as the seeded admin account."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@smartdecor.dev", "password": "Admin123!"},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}
