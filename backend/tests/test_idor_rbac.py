"""Stage 03 · object-level and function-level authorisation (OWASP A01).

Probe checks A-01 … A-06. Every test creates two *real* tenants and has one try
to reach the other's object, plus the role matrix for every privileged route.
The rule the suite enforces: a cross-tenant read is a **404**, never a 403 —
confirming that an object exists is itself a disclosure.
"""
from __future__ import annotations

import uuid

import pytest

QUIZ_BODY = {
    # Stage 04: quiz colors must be #RRGGBB (was "warm" before the schema tightening)
    "styles": ["modern"], "color_palette": ["#D9A05B"],
    "room_width_cm": 400, "room_length_cm": 500,
    "budget_min_toman": 1_000_000, "budget_max_toman": 9_000_000,
    "materials": ["wood"], "patterns": ["solid"],
}


def _make_moodboard(client, headers, title="mine"):
    resp = client.post("/api/v1/moodboards", headers=headers,
                       json={"title": title, "items": [], "shopping_list": []})
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


def _make_quiz(client, headers):
    resp = client.post("/api/v1/quiz", headers=headers, json=QUIZ_BODY)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


def _make_project(client, headers, name="proj"):
    resp = client.post("/api/v1/projects", headers=headers, json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


# ------------------------------------------------------------------ moodboards

def test_moodboard_is_not_readable_by_another_user(client, make_user):
    owner, attacker = make_user(), make_user()
    board_id = _make_moodboard(client, owner["headers"], "secret board")

    resp = client.get(f"/api/v1/moodboards/{board_id}", headers=attacker["headers"])
    assert resp.status_code == 404, resp.text
    assert "secret board" not in resp.text


def test_moodboard_is_not_writable_by_another_user(client, make_user):
    owner, attacker = make_user(), make_user()
    board_id = _make_moodboard(client, owner["headers"])

    patched = client.patch(f"/api/v1/moodboards/{board_id}",
                           headers=attacker["headers"], json={"title": "pwned"})
    assert patched.status_code == 404, patched.text

    deleted = client.delete(f"/api/v1/moodboards/{board_id}",
                            headers=attacker["headers"])
    assert deleted.status_code == 404, deleted.text

    still_there = client.get(f"/api/v1/moodboards/{board_id}",
                             headers=owner["headers"])
    assert still_there.status_code == 200
    assert still_there.json()["data"]["title"] != "pwned"


def test_moodboard_listing_only_returns_your_own(client, make_user):
    owner, other = make_user(), make_user()
    _make_moodboard(client, owner["headers"], "owner-board")
    resp = client.get("/api/v1/moodboards", headers=other["headers"])
    assert resp.status_code == 200
    assert all(b["title"] != "owner-board" for b in resp.json()["data"])


# ----------------------------------------------------------------------- quiz

def test_quiz_is_not_readable_by_another_user(client, make_user):
    owner, attacker = make_user(), make_user()
    quiz_id = _make_quiz(client, owner["headers"])
    resp = client.get(f"/api/v1/quiz/{quiz_id}", headers=attacker["headers"])
    assert resp.status_code == 404, resp.text


# -------------------------------------------------------------------- projects

def test_project_is_not_readable_by_another_designer(client, make_user):
    owner, attacker = make_user("designer"), make_user("designer")
    project_id = _make_project(client, owner["headers"], "confidential")
    resp = client.get(f"/api/v1/projects/{project_id}", headers=attacker["headers"])
    assert resp.status_code == 404, resp.text
    assert "confidential" not in resp.text


def test_project_is_not_deletable_by_another_designer(client, make_user):
    owner, attacker = make_user("designer"), make_user("designer")
    project_id = _make_project(client, owner["headers"])
    assert client.delete(f"/api/v1/projects/{project_id}",
                         headers=attacker["headers"]).status_code == 404
    assert client.get(f"/api/v1/projects/{project_id}",
                      headers=owner["headers"]).status_code == 200


def test_cannot_share_someone_elses_project(client, make_user):
    owner, attacker = make_user("designer"), make_user("designer")
    project_id = _make_project(client, owner["headers"])
    quiz_id = _make_quiz(client, attacker["headers"])
    resp = client.post(f"/api/v1/projects/{project_id}/share",
                       headers=attacker["headers"],
                       json={"quiz_id": quiz_id, "expires_days": 7})
    assert resp.status_code == 404, resp.text


def test_cannot_share_someone_elses_quiz(client, make_user):
    """Owning the project is not enough — the quiz must be yours too."""
    owner, victim = make_user("designer"), make_user("designer")
    project_id = _make_project(client, owner["headers"])
    victim_quiz = _make_quiz(client, victim["headers"])
    resp = client.post(f"/api/v1/projects/{project_id}/share",
                       headers=owner["headers"],
                       json={"quiz_id": victim_quiz, "expires_days": 7})
    assert resp.status_code == 404, resp.text


# ------------------------------------------------------------ unknown/forged ids

@pytest.mark.parametrize("path", [
    "/api/v1/moodboards/{}", "/api/v1/quiz/{}", "/api/v1/projects/{}",
])
@pytest.mark.parametrize("ident", [
    uuid.uuid4().hex, "1", "0", "../../etc/passwd", "' OR '1'='1",
    "%2e%2e%2f", "a" * 500,
])
def test_hostile_identifiers_never_500(client, make_user, path, ident):
    user = make_user("designer")
    resp = client.get(path.format(ident), headers=user["headers"])
    assert resp.status_code in (404, 422), f"{path.format(ident)} -> {resp.status_code}"


# --------------------------------------------------------------- role matrix

ADMIN_ONLY = [
    ("GET", "/api/v1/admin/users"),
    ("GET", "/api/v1/admin/subscriptions"),
    ("GET", "/api/v1/admin/stats"),
    ("GET", "/api/v1/products"),
]


@pytest.mark.parametrize(("method", "path"), ADMIN_ONLY)
def test_admin_routes_reject_a_homeowner(client, make_user, method, path):
    user = make_user("homeowner")
    resp = client.request(method, path, headers=user["headers"])
    assert resp.status_code == 403, resp.text


@pytest.mark.parametrize(("method", "path"), ADMIN_ONLY)
def test_admin_routes_reject_anonymous(client, method, path):
    assert client.request(method, path).status_code == 401


def test_admin_routes_reject_a_designer(client, make_user):
    designer = make_user("designer")
    resp = client.get("/api/v1/admin/users", headers=designer["headers"])
    assert resp.status_code == 403


def test_designer_routes_reject_a_homeowner(client, make_user):
    user = make_user("homeowner")
    assert client.get("/api/v1/projects", headers=user["headers"]).status_code == 403
    assert client.post("/api/v1/projects", headers=user["headers"],
                       json={"name": "nope"}).status_code == 403


def test_product_mutation_requires_admin(client, make_user):
    designer = make_user("designer")
    for method, path in (
        ("POST", "/api/v1/products"),
        ("PATCH", "/api/v1/products/whatever"),
        ("DELETE", "/api/v1/products/whatever"),
        ("POST", "/api/v1/products/whatever/verify"),
    ):
        resp = client.request(method, path, headers=designer["headers"], json={})
        assert resp.status_code == 403, f"{method} {path} -> {resp.status_code}"


def test_role_is_read_from_the_database_not_from_the_token(client, db, make_user):
    """Privilege comes from the row, not from a claim a client could forge.

    A token minted before a demotion must stop working the moment the row
    changes — proving the role is not cached in the JWT.
    """
    from app.models.user import User

    actor = make_user("designer")
    assert client.get("/api/v1/projects",
                      headers=actor["headers"]).status_code == 200

    user = db.get(User, actor["user"]["id"])
    user.role = "homeowner"
    db.commit()

    resp = client.get("/api/v1/projects", headers=actor["headers"])
    assert resp.status_code == 403, "the old token still carried designer power"


def test_forged_role_claim_is_ignored(client, make_user):
    """Adding `"role": "admin"` to the JWT payload must change nothing."""
    import json
    import time

    import jwt

    from app.core.config import settings

    actor = make_user("homeowner")
    forged = jwt.encode(
        {
            "sub": actor["user"]["id"], "type": "access", "role": "admin",
            "is_admin": True, "jti": "forged", "iat": int(time.time()),
            "exp": int(time.time()) + 600,
        },
        settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM,
    )
    assert "admin" in json.dumps({"role": "admin"})  # readability guard
    resp = client.get("/api/v1/admin/users",
                      headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 403, resp.text


# ----------------------------------------------------------------- admin power

def test_admin_cannot_change_their_own_role(client, admin_user):
    """Prevents an admin from locking the platform out of its own admin set."""
    resp = client.patch(f"/api/v1/admin/users/{admin_user['user']['id']}",
                        headers=admin_user["headers"], json={"role": "homeowner"})
    assert resp.status_code == 409, resp.text


def test_admin_cannot_deactivate_themselves(client, admin_user):
    resp = client.patch(f"/api/v1/admin/users/{admin_user['user']['id']}",
                        headers=admin_user["headers"], json={"is_active": False})
    assert resp.status_code == 409, resp.text


def test_the_last_admin_cannot_be_demoted(client, admin_user, db):
    """There must always be someone who can administer the platform."""
    from sqlalchemy import func, select

    from app.models.user import User

    admins = db.scalar(select(func.count()).select_from(User).where(
        User.role == "admin", User.is_active.is_(True)))
    if admins != 1:
        pytest.skip(f"fixture database has {admins} active admins")
    resp = client.patch(f"/api/v1/admin/users/{admin_user['user']['id']}",
                        headers=admin_user["headers"], json={"role": "designer"})
    assert resp.status_code == 409


def test_admin_patch_rejects_unknown_fields(client, admin_user, make_user):
    victim = make_user()
    resp = client.patch(f"/api/v1/admin/users/{victim['user']['id']}",
                        headers=admin_user["headers"],
                        json={"hashed_password": "x", "email": "new@example.com"})
    assert resp.status_code == 422, resp.text


def test_admin_patch_rejects_an_invalid_role(client, admin_user, make_user):
    victim = make_user()
    resp = client.patch(f"/api/v1/admin/users/{victim['user']['id']}",
                        headers=admin_user["headers"], json={"role": "superuser"})
    assert resp.status_code == 422, resp.text


def test_role_changes_are_audited(client, admin_user, make_user, db):
    from sqlalchemy import select

    from app.models.audit_log import ACTION_ROLE_CHANGE, AuditLog

    victim = make_user("homeowner")
    resp = client.patch(f"/api/v1/admin/users/{victim['user']['id']}",
                        headers=admin_user["headers"], json={"role": "designer"})
    assert resp.status_code == 200, resp.text

    rows = db.scalars(select(AuditLog).where(
        AuditLog.action == ACTION_ROLE_CHANGE).order_by(
        AuditLog.created_at.desc())).all()
    assert rows, "a role change must leave an audit trail"
    latest = rows[0]
    assert latest.user_id == admin_user["user"]["id"], "the actor must be recorded"
    assert "homeowner" in latest.detail and "designer" in latest.detail
