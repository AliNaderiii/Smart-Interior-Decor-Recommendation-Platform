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
# Stage 03 (IR-001): demo accounts are no longer created by default in any
# environment. The suite depends on them (`admin_headers`, `demo_user`), so it
# opts in **explicitly** — which is exactly the mechanism a developer uses
# locally, and exactly the mechanism production can never enable.
os.environ.setdefault("SEED_DEMO_ACCOUNTS", "true")
# TestClient talks plain HTTP, and httpx (correctly) refuses to store `Secure`
# cookies over http:// — so exercise the cookie path with Secure off.
os.environ.setdefault("COOKIE_SECURE", "false")

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


# ---------------------------------------------------------------- V2 fixtures

@pytest.fixture()
def demo_user():
    """Credentials of the seeded homeowner account."""
    return {"email": "demo@smartdecor.dev", "password": "Demo1234!"}


@pytest.fixture()
def bearer_headers(auth_headers):
    """Just the Authorization header (auth_headers returns a (headers, data) tuple)."""
    return auth_headers[0]


# ------------------------------------------------------------ Stage 03 fixtures

def _register(client, role: str = "homeowner") -> dict:
    """Register a throwaway account and return headers + the user payload.

    Registration is rate limited to 3/min/IP and `_clear_cache` flushes Redis
    before every test, so a test may create at most three accounts this way.
    """
    import uuid

    email = f"sec-{uuid.uuid4().hex[:10]}@example.com"
    resp = client.post("/api/v1/auth/register", json={
        "email": email, "password": "Str0ngTestPassphrase!", "full_name": "Sec Test",
        "role": role,
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    return {
        "email": email,
        "password": "Str0ngTestPassphrase!",
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
        "user": data["user"],
        "tokens": data,
    }


@pytest.fixture()
def make_user(client):
    """Factory so a test can create exactly the identities it needs."""
    def _factory(role: str = "homeowner"):
        return _register(client, role)
    return _factory


@pytest.fixture()
def homeowner(make_user):
    return make_user("homeowner")


@pytest.fixture()
def designer(make_user):
    return make_user("designer")


@pytest.fixture()
def admin_user(client, db):
    """The seeded admin, as a dict shaped like `make_user` output."""
    resp = client.post("/api/v1/auth/login", json={
        "email": "admin@smartdecor.dev", "password": "Admin123!"})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    return {
        "email": "admin@smartdecor.dev",
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
        "user": data["user"],
    }


@pytest.fixture()
def png_bytes():
    """A real, tiny PNG produced by Pillow (not a hand-written header)."""
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (32, 24), (200, 120, 40)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture()
def reset_settings():
    """Restore mutated Settings attributes after a test."""
    from app.core.config import settings as live

    saved: dict = {}

    def _set(**kwargs):
        for key, value in kwargs.items():
            saved.setdefault(key, getattr(live, key))
            object.__setattr__(live, key, value)

    yield _set
    for key, value in saved.items():
        object.__setattr__(live, key, value)
