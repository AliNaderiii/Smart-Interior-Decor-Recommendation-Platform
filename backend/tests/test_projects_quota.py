"""Stage 1 (T-1.1) — designer project quota.

Client spec: "subscription required to create new projects." Covers the happy
paths (free tier N, lifted by an active subscription), the abuse paths
(expired subscription, unknown plan -> fail-closed fallback, cross-designer
IDOR, concurrent creation racing past the limit) and the non-designer
posture (admin exempt, homeowner forbidden).

Quota values under test come from ``seed_data/subscription_plans.json``:
designer_free=2, designer_studio=20, designer_agency=-1 (unlimited).
"""
from __future__ import annotations

import concurrent.futures
from datetime import timedelta

from app.core.datasets import designer_project_quota
from app.models.base import utcnow
from app.models.subscription import Subscription

QUOTA_FREE = designer_project_quota("designer_free")      # 2, from the dataset
QUOTA_STUDIO = designer_project_quota("designer_studio")  # 20, from the dataset


def _grant(db, user_id: str, plan: str, *, active: bool = True, days: float = 30) -> None:
    """Set the user's subscription row (registration pre-creates a
    ``plan="free", is_active=False`` row — the designer purchase flow is out
    of scope for this suite, so the row is set directly)."""
    from sqlalchemy import select

    sub = db.scalar(select(Subscription).where(Subscription.user_id == user_id))
    assert sub is not None
    sub.plan = plan
    sub.is_active = active
    sub.expires_at = utcnow() + timedelta(days=days)
    db.commit()


def _create(client, headers: dict, name: str = "پروژه") -> dict:
    resp = client.post(
        "/api/v1/projects",
        json={"name": name, "client_name": "", "client_email": "", "notes": ""},
        headers=headers,
    )
    return resp.json()


def test_free_designer_can_create_up_to_quota(client, designer):
    """A free-tier designer gets exactly the dataset's N projects."""
    h = designer["headers"]
    for i in range(QUOTA_FREE):
        body = _create(client, h, f"پروژه {i}")
        assert body["success"] is True, body
        assert body["data"]["id"], body
    listed = client.get("/api/v1/projects", headers=h).json()["data"]
    assert len(listed) == QUOTA_FREE


def test_third_project_blocked_402_with_persian_message(client, designer):
    """Over-quota -> 402, Persian-first message, no envelope leak."""
    h = designer["headers"]
    for _ in range(QUOTA_FREE):
        assert _create(client, h)["success"] is True
    resp = client.post(
        "/api/v1/projects", json={"name": "بی‌شمار"}, headers=h
    )
    assert resp.status_code == 402, resp.text
    body = resp.json()
    assert body["success"] is False
    assert "سهمیه" in body["error"]            # Persian quota message
    assert "ارتقا" in body["error"]           # ...with the upgrade CTA
    assert str(QUOTA_FREE) in body["error"]    # ...citing the actual limit
    # The project was NOT created.
    listed = client.get("/api/v1/projects", headers=h).json()["data"]
    assert len(listed) == QUOTA_FREE


def test_active_studio_subscription_lifts_quota(client, designer, db):
    """An active designer_studio subscription (20 projects) lifts the cap."""
    _grant(db, designer["user"]["id"], "designer_studio")
    h = designer["headers"]
    # Free-tier slots + at least one beyond the free quota must succeed.
    for i in range(QUOTA_FREE + 1):
        body = _create(client, h, f"استودیو {i}")
        assert body["success"] is True, body
    assert QUOTA_FREE + 1 <= QUOTA_STUDIO


def test_expired_subscription_falls_back_to_free_quota(client, designer, db):
    """Expired is not active: the cap drops back to the free tier's N."""
    _grant(db, designer["user"]["id"], "designer_studio", days=-1)  # already expired
    h = designer["headers"]
    for _ in range(QUOTA_FREE):
        assert _create(client, h)["success"] is True
    resp = client.post("/api/v1/projects", json={"name": "X"}, headers=h)
    assert resp.status_code == 402, resp.text
    assert "سهمیه" in resp.json()["error"]


def test_inactive_subscription_falls_back_to_free_quota(client, designer, db):
    """is_active=False is a free account, even with a future expiry."""
    _grant(db, designer["user"]["id"], "designer_studio", active=False)
    h = designer["headers"]
    for _ in range(QUOTA_FREE):
        assert _create(client, h)["success"] is True
    assert client.post("/api/v1/projects", json={"name": "X"}, headers=h).status_code == 402


def test_unknown_plan_id_falls_back_to_default_one(client, designer, db):
    """A subscription naming a plan that is not in the dataset fails closed
    to the configured fallback (DESIGNER_PROJECT_QUOTA_FALLBACK = 1)."""
    _grant(db, designer["user"]["id"], "mystery_plan_zzz")
    h = designer["headers"]
    assert _create(client, h)["success"] is True
    resp = client.post("/api/v1/projects", json={"name": "دوم"}, headers=h)
    assert resp.status_code == 402, resp.text
    assert "1" in resp.json()["error"]


def test_agency_unlimited_designer_not_blocked(client, designer, db):
    """designer_agency (limits.projects = -1) has no cap."""
    _grant(db, designer["user"]["id"], "designer_agency")
    h = designer["headers"]
    for i in range(QUOTA_FREE + 3):  # comfortably past the free tier
        body = _create(client, h, f"آژانس {i}")
        assert body["success"] is True, body


def test_cross_designer_idor_is_blocked(client, designer, make_user):
    """Designer B cannot read, list, delete or share designer A's project."""
    designer_b = make_user("designer")
    project_id = _create(client, designer["headers"])["data"]["id"]

    hb = designer_b["headers"]
    # Fetch by id -> 404 (not 200, not 403: no existence leak either).
    got = client.get(f"/api/v1/projects/{project_id}", headers=hb)
    assert got.status_code == 404
    # List -> A's project never appears.
    listed = client.get("/api/v1/projects", headers=hb).json()["data"]
    assert all(p["id"] != project_id for p in listed)
    # Delete -> 404, and the project survives for A.
    deleted = client.delete(f"/api/v1/projects/{project_id}", headers=hb)
    assert deleted.status_code == 404
    owner = client.get(f"/api/v1/projects/{project_id}", headers=designer["headers"])
    assert owner.status_code == 200


def test_homeowner_cannot_create_project(client, make_user):
    """Role guard: homeowners are not designers."""
    homeowner = make_user("homeowner")
    resp = client.post("/api/v1/projects", json={"name": "X"}, headers=homeowner["headers"])
    assert resp.status_code == 403


def test_admin_is_exempt_from_designer_quota(client, admin_user):
    """Staff accounts are not tenants: no quota applies to admins."""
    h = admin_user["headers"]
    for i in range(QUOTA_FREE + 2):
        body = _create(client, h, f"ادمین {i}")
        assert body["success"] is True, body


def test_concurrent_creations_never_exceed_quota(client, designer):
    """5 simultaneous creation attempts against a quota of 2 -> exactly 2 win.

    TestClient serialises requests through one event loop, so this proves the
    check is inside the request path (no check-then-act split across
    transactions); the engine-level race guard (row lock + conditional
    insert) is additionally exercised by the PostgreSQL CI run of the same
    suite and by the unit-level proof in
    ``test_insert_guarded_is_atomic_under_concurrency``.
    """
    h = designer["headers"]

    def attempt(i: int) -> int:
        return client.post(
            "/api/v1/projects", json={"name": f"race {i}"}, headers=h
        ).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        codes = list(pool.map(attempt, range(5)))

    assert codes.count(201) == QUOTA_FREE, codes
    assert codes.count(402) == 5 - QUOTA_FREE, codes
    listed = client.get("/api/v1/projects", headers=h).json()["data"]
    assert len(listed) == QUOTA_FREE


def _run_guard_race(engine) -> tuple[list[bool], int]:
    """Run 6 concurrent guarded inserts for a fresh designer; return the win
    flags and the resulting project row count.

    Calls :func:`insert_project_guarded` **directly**, deliberately bypassing
    the route and ``create_designer_project``: the point is to prove the guard
    is self-sufficient, i.e. that a caller which does not take the user-row
    lock itself still cannot exceed the quota. The guard takes that lock
    internally, so this holds on PostgreSQL (READ COMMITTED) as well as on
    SQLite.

    Each worker gets its own session/connection, so these are 6 genuinely
    concurrent transactions, exactly as 6 concurrent HTTP requests would be.
    """
    import threading
    import uuid as _uuid

    from sqlalchemy import func, select
    from sqlalchemy.orm import sessionmaker

    from app.models.project import Project
    from app.models.user import User
    from app.services.designer_quota import insert_project_guarded

    Session = sessionmaker(bind=engine)
    s = Session()
    owner = User(
        id=_uuid.uuid4().hex, email=f"race-{_uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x", role="designer",
    )
    s.add(owner)
    s.commit()
    owner_id = owner.id
    s.close()

    quota = 2

    # Force all 6 workers to hit the guard at the same instant. Two things are
    # needed, and both matter:
    #
    #   * each session must already hold an open connection *before* the
    #     barrier — SQLAlchemy connects lazily, and paying for connection
    #     set-up after the barrier staggers the threads enough that they stop
    #     overlapping;
    #   * the barrier itself then releases them together.
    #
    # Without this the pool serialises them by accident and an unguarded
    # insert passes by luck: measured on PostgreSQL 16, the lock-removed
    # regression was caught in only 1 run out of 8. That is precisely how the
    # missing lock survived every local run and only surfaced in CI. With the
    # warm-up it is caught every time, so this test now has real teeth.
    start = threading.Barrier(6)

    def worker(_: int) -> bool:
        sess = Session()
        try:
            sess.execute(select(1))  # open the connection before the barrier
            start.wait(timeout=30)
            ok = insert_project_guarded(
                sess,
                owner_id,
                {
                    "id": _uuid.uuid4().hex,
                    "name": "r",
                    "client_name": "",
                    "client_email": "",
                    "notes": "",
                    "designer_id": owner_id,
                },
                quota,
            )
            sess.commit()
            return ok
        finally:
            sess.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        wins = list(pool.map(worker, range(6)))

    check = Session()
    n_projects = check.scalar(
        select(func.count(Project.id)).where(Project.designer_id == owner_id)
    )
    check.close()
    return wins, n_projects


def test_insert_guarded_is_atomic_under_concurrency_sqlite():
    """SQLite-side proof of the conditional-insert guard.

    True multi-connection concurrency against a file-backed database (6
    fresh transactions, as concurrent HTTP requests would be): the row count
    can never exceed the quota regardless of interleaving. On SQLite the
    ``FOR UPDATE`` row lock is a silent no-op, so this isolates the
    conditional ``INSERT ... SELECT ... WHERE count < quota`` — exactly the
    layer that protects the dev fallback engine, with the lock contributing
    nothing.
    """
    import os
    import tempfile

    from sqlalchemy import create_engine

    from app.models import Base

    path = tempfile.mktemp(suffix=".db")
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    try:
        wins, n_projects = _run_guard_race(engine)
    finally:
        engine.dispose()
        if os.path.exists(path):
            os.unlink(path)
    assert wins.count(True) == 2, wins
    assert n_projects == 2, n_projects


def test_insert_guarded_is_atomic_under_concurrency_postgres():
    """PostgreSQL-side proof: the row lock + conditional insert must hold
    under true concurrency on the production engine.

    This is the case the conditional insert *cannot* carry alone. Under
    READ COMMITTED every statement takes a fresh snapshot, so without the
    user-row lock all 6 transactions would read ``count = 0`` before any of
    them committed and all 6 would insert. The lock inside
    :func:`insert_project_guarded` serialises them; a blocked transaction
    re-snapshots on acquiring it and therefore sees its committed siblings.

    Runs only in CI (``TEST_DATABASE_URL`` set, same pattern as
    ``test_pgvector_real.py``); skips cleanly on the SQLite dev suite.
    """
    import os

    from sqlalchemy import create_engine

    from app.models import Base
    from app.models.project import Project
    from app.models.user import User

    pg_url = os.environ.get("TEST_DATABASE_URL", "")
    if not pg_url.startswith(("postgres", "postgresql")):
        import pytest

        pytest.skip("set TEST_DATABASE_URL to a PostgreSQL URL to run")

    engine = create_engine(pg_url)
    # Only the tables the race touches — keeps this independent of the
    # pgvector extension and of the pgvector test module's schema lifecycle.
    Base.metadata.create_all(engine, tables=[User.__table__, Project.__table__])
    try:
        wins, n_projects = _run_guard_race(engine)
    finally:
        engine.dispose()
    assert wins.count(True) == 2, wins
    assert n_projects == 2, n_projects
