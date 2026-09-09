"""P4-B · administrative account erasure — ``DELETE /admin/users/{user_id}``.

Mirrors ``tests/test_gdpr.py`` (the data subject's own erasure) and adds the
administrator-specific contract: RBAC, the two 409 guards, the second audit
row under the actor, and the promise that neither audit row nor the response
carries the erased e-mail in plaintext.

Registration is rate limited to 3/min/IP (see ``conftest._register``), so no
test here creates more than three throwaway accounts.
"""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models.audit_log import ACTION_USER_DELETE, AuditLog
from app.models.feedback import ProductFeedback
from app.models.moodboard import Moodboard
from app.models.project import Project, ShareLink
from app.models.quiz import StyleQuiz
from app.models.subscription import Subscription
from app.models.user import User
from app.services import erasure

QUIZ_BODY = {
    "styles": ["modern"], "color_palette": [], "room_width_cm": 300,
    "room_length_cm": 300, "budget_min_toman": 0, "budget_max_toman": 100,
    "materials": [], "patterns": [],
}


def _populate(client, headers):
    assert client.post("/api/v1/quiz", headers=headers, json=QUIZ_BODY).status_code == 201
    assert client.post(
        "/api/v1/moodboards", headers=headers,
        json={"title": "board", "items": [], "shopping_list": []},
    ).status_code == 201


def _delete(client, admin, user_id: str, **params):
    return client.delete(f"/api/v1/admin/users/{user_id}", headers=admin["headers"],
                         params=params or None)


def _rows(db, model, column, value) -> int:
    return db.scalar(select(func.count()).select_from(model).where(column == value))


# ------------------------------------------------------------------- RBAC

def test_anonymous_cannot_delete(client):
    # No `make_user` here on purpose: registering through the TestClient leaves
    # the httpOnly session cookies in its jar, and the "anonymous" call would
    # then be a cookie-authenticated homeowner (403), not an anonymous one.
    assert client.delete(f"/api/v1/admin/users/{'0' * 32}").status_code == 401


@pytest.mark.parametrize("role", ["homeowner", "designer"])
def test_non_admins_cannot_delete(client, make_user, role):
    actor = make_user(role)
    victim = make_user()
    resp = client.delete(f"/api/v1/admin/users/{victim['user']['id']}",
                         headers=actor["headers"])
    assert resp.status_code == 403, resp.text
    # and the victim is still there
    assert client.get("/api/v1/auth/me", headers=victim["headers"]).status_code == 200


def test_unknown_id_is_404(client, admin_user):
    assert _delete(client, admin_user, "0" * 32).status_code == 404
    assert _delete(client, admin_user, "../../etc/passwd").status_code == 404


# ------------------------------------------------------------ the two guards

def test_admin_cannot_delete_itself(client, admin_user, db):
    resp = _delete(client, admin_user, admin_user["user"]["id"])
    assert resp.status_code == 409, resp.text
    assert db.get(User, admin_user["user"]["id"]) is not None


def test_last_active_admin_cannot_be_removed_through_the_service_guard(client, admin_user, db):
    """The HTTP path always has the actor as a second admin; exercise the
    guard directly the way a CLI or a service principal would hit it."""
    from app.api.routes.admin import _count_other_active_admins

    admins = db.scalar(select(func.count()).select_from(User).where(
        User.role == "admin", User.is_active.is_(True)))
    if admins != 1:
        pytest.skip(f"fixture database has {admins} active admins")
    assert _count_other_active_admins(db, admin_user["user"]["id"]) == 0


def test_an_inactive_admin_can_be_removed(client, admin_user, make_user, db):
    """A deactivated administrator is not 'the last active one'."""
    other = make_user("designer")
    uid = other["user"]["id"]
    row = db.get(User, uid)
    row.role, row.is_active = "admin", False
    db.commit()

    resp = _delete(client, admin_user, uid)
    assert resp.status_code == 200, resp.text
    db.expire_all()
    assert db.get(User, uid) is None


# ------------------------------------------------------------------ cascade

def test_erasure_removes_every_owned_row(client, admin_user, make_user, db):
    designer = make_user("designer")
    uid = designer["user"]["id"]
    _populate(client, designer["headers"])
    project = client.post("/api/v1/projects", headers=designer["headers"],
                          json={"name": "villa"}).json()["data"]
    quiz = client.post("/api/v1/quiz", headers=designer["headers"],
                       json={**QUIZ_BODY, "project_id": project["id"]}).json()["data"]
    share = client.post(f"/api/v1/projects/{project['id']}/share", headers=designer["headers"],
                        json={"quiz_id": quiz["id"], "expires_days": 7})
    assert share.status_code == 201, share.text

    assert _rows(db, Subscription, Subscription.user_id, uid) == 1
    assert _rows(db, ShareLink, ShareLink.created_by, uid) == 1

    resp = _delete(client, admin_user, uid)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["id"] == uid

    db.expire_all()
    assert db.get(User, uid) is None
    for model, column in (
        (StyleQuiz, StyleQuiz.user_id), (Moodboard, Moodboard.user_id),
        (ProductFeedback, ProductFeedback.user_id), (Project, Project.designer_id),
        (ShareLink, ShareLink.created_by), (Subscription, Subscription.user_id),
    ):
        assert _rows(db, model, column, uid) == 0, f"{model.__name__} rows survived erasure"


def test_the_erased_session_stops_working(client, admin_user, make_user):
    victim = make_user()
    assert client.get("/api/v1/auth/me", headers=victim["headers"]).status_code == 200
    assert _delete(client, admin_user, victim["user"]["id"]).status_code == 200
    assert client.get("/api/v1/auth/me", headers=victim["headers"]).status_code == 401
    # the refresh token is dead too: the subject no longer exists
    resp = client.post("/api/v1/auth/refresh",
                       json={"refresh_token": victim["tokens"]["refresh_token"]})
    assert resp.status_code == 401, resp.text


def test_deleting_twice_is_404(client, admin_user, make_user):
    victim = make_user()
    assert _delete(client, admin_user, victim["user"]["id"]).status_code == 200
    assert _delete(client, admin_user, victim["user"]["id"]).status_code == 404


# ---------------------------------------------------------------- audit trail

def test_audit_trail_is_pseudonymised_and_actor_is_recorded(client, admin_user, make_user, db):
    victim = make_user()
    uid, email = victim["user"]["id"], victim["email"]
    _populate(client, victim["headers"])
    before = _rows(db, AuditLog, AuditLog.user_id, uid)
    assert before > 0, "the fixture should have produced audit rows"

    resp = _delete(client, admin_user, uid, reason="probe account")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    pseudonym = data["audit_pseudonym"]
    assert pseudonym == erasure.pseudonym_for(uid)
    assert data["audit_rows_pseudonymised"] == before
    assert email not in resp.text, "the response must not echo the erased address"

    db.expire_all()
    # G-02 semantics preserved: nothing left under the real id, trail survives.
    assert _rows(db, AuditLog, AuditLog.user_id, uid) == 0
    trail = db.scalars(select(AuditLog).where(AuditLog.user_id == pseudonym)).all()
    assert len(trail) >= before + 1
    for row in trail:
        assert row.user_agent == ""
        assert row.ip in ("", "0.0.0.0") or row.ip.endswith(".0"), row.ip
    subject_row = [r for r in trail if r.action == ACTION_USER_DELETE]
    assert len(subject_row) == 1
    assert subject_row[0].detail.startswith(erasure.ADMIN_DETAIL)
    assert "probe account" in subject_row[0].detail

    # The actor's accountability row: who deleted whom (pseudonymously).
    actor_rows = db.scalars(select(AuditLog).where(
        AuditLog.action == ACTION_USER_DELETE,
        AuditLog.user_id == admin_user["user"]["id"],
    ).order_by(AuditLog.created_at.desc())).all()
    assert actor_rows, "the administrator's action must leave a trail under the actor"
    latest = actor_rows[0]
    assert f"target={pseudonym}" in latest.detail
    assert data["email_pseudonym"] in latest.detail
    assert "reason=probe account" in latest.detail
    assert email not in latest.detail and uid not in latest.detail

    # The e-mail pseudonym leaks at most the first character and the domain.
    local, _, domain = email.partition("@")
    assert data["email_pseudonym"].startswith(f"{local[0]}***@{domain}#")


def test_self_service_and_admin_erasure_share_one_implementation(client, make_user, db):
    """Guards against the cascades drifting apart again: the subject-side
    ``user_delete`` row is written by the same code for both callers."""
    actor = make_user()
    uid = actor["user"]["id"]
    resp = client.delete("/api/v1/users/me", headers=actor["headers"])
    assert resp.status_code == 200, resp.text
    pseudonym = resp.json()["data"]["audit_pseudonym"]
    assert pseudonym == erasure.pseudonym_for(uid)

    db.expire_all()
    row = db.scalars(select(AuditLog).where(
        AuditLog.action == ACTION_USER_DELETE, AuditLog.user_id == pseudonym)).first()
    assert row is not None
    assert row.detail == erasure.SELF_SERVICE_DETAIL


def test_reason_is_bounded(client, admin_user, make_user):
    victim = make_user()
    resp = _delete(client, admin_user, victim["user"]["id"], reason="x" * 201)
    assert resp.status_code == 422, resp.text


# ------------------------------------------------------------ redis purge

def test_redis_keys_for_the_user_are_purged(client, admin_user, make_user):
    from app.core.redis_client import get_redis

    victim = make_user()
    uid = victim["user"]["id"]
    redis = get_redis()
    redis.set(f"rec:{uid}:abc", "cached")
    redis.set(f"rl:rec:{uid}", "3")
    redis.set("rec:someone-else:abc", "keep")

    resp = _delete(client, admin_user, uid)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["redis_keys_purged"] >= 2
    assert redis.get(f"rec:{uid}:abc") is None
    assert redis.get(f"rl:rec:{uid}") is None
    assert redis.get("rec:someone-else:abc") is not None


def test_a_redis_outage_does_not_block_the_erasure(client, admin_user, make_user, monkeypatch, db):
    victim = make_user()
    uid = victim["user"]["id"]

    class Down:
        def scan_iter(self, *_a, **_k):
            raise ConnectionError("redis down")

        def delete(self, *_a, **_k):
            raise ConnectionError("redis down")

    import app.core.redis_client as redis_client

    monkeypatch.setattr(redis_client, "get_redis", lambda: Down())
    resp = _delete(client, admin_user, uid)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["redis_keys_purged"] is None
    db.expire_all()
    assert db.get(User, uid) is None


# ------------------------------------------------- operator CLI (selection)

def test_purge_cli_selection_respects_every_rail():
    from scripts.purge_accounts import select_targets

    users = [
        {"id": "a", "email": "admin@smartdecor.dev", "role": "admin"},
        {"id": "b", "email": "probe-1@example.com", "role": "homeowner"},
        {"id": "c", "email": "sec-x@EXAMPLE.com", "role": "designer"},
        {"id": "d", "email": "boss@example.com", "role": "admin"},
        {"id": "e", "email": "real@gmail.com", "role": "homeowner"},
        {"id": "f", "email": "me@example.com", "role": "admin"},
    ]
    plan = select_targets(users, match=["*@example.com"], protect=["*@smartdecor.dev"],
                          actor_id="f")
    assert [u["id"] for u in plan.targets] == ["b", "c"], "glob is case-insensitive"
    reasons = {u["id"]: why for u, why in plan.skipped}
    assert "administrator" in reasons["d"]
    assert reasons["f"] == "acting administrator"
    assert "a" not in reasons and "e" not in reasons, "non-matching rows are not even listed"

    with_admins = select_targets(users, match=["*@example.com"], protect=[], actor_id="f",
                                 include_admins=True)
    assert [u["id"] for u in with_admins.targets] == ["b", "c", "d"]
    assert dict((u["id"], w) for u, w in with_admins.skipped) == {"f": "acting administrator"}


def test_purge_cli_end_to_end_against_the_test_app(client, admin_user, make_user, monkeypatch, capsys):
    """Drive the CLI with the app's own TestClient as transport: dry-run
    deletes nothing, ``--yes`` deletes exactly the matching accounts."""
    from fastapi.testclient import TestClient

    from app.main import app
    from scripts import purge_accounts

    victims = [make_user(), make_user("designer")]
    victim_ids = {v["user"]["id"] for v in victims}

    class AppClient(TestClient):  # an httpx.Client bound to the ASGI app
        def __init__(self, *, base_url: str, timeout: float):
            super().__init__(app, base_url=base_url)

    monkeypatch.setattr(purge_accounts.httpx, "Client", AppClient)
    token = admin_user["headers"]["Authorization"].split(" ", 1)[1]
    argv = ["--api", "http://testserver/api/v1", "--match", "sec-*@example.com",
            "--token", token, "--reason", "cli test"]

    assert purge_accounts.main(argv) == 0
    out = capsys.readouterr().out
    assert "dry-run: nothing deleted" in out
    for v in victims:
        assert client.get("/api/v1/auth/me", headers=v["headers"]).status_code == 200

    assert purge_accounts.main(argv + ["--yes"]) == 0
    out = capsys.readouterr().out
    assert out.count("  ok     ") >= 2
    for v in victims:
        assert client.get("/api/v1/auth/me", headers=v["headers"]).status_code == 401
    listed = {u["id"] for u in client.get("/api/v1/admin/users",
                                          headers=admin_user["headers"]).json()["data"]}
    assert not (victim_ids & listed)
    assert admin_user["user"]["id"] in listed, "the seeded admin is protected"
