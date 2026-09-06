"""Designer workflow (migration 0005) — project status + client approvals.

Commit 44d9e91 added three endpoints with no test coverage at all, one of
them an **unauthenticated write** (``POST /share/{token}/approve``). This
suite pins the contract:

* ``PATCH /projects/{id}/status`` — designer-only, owner-only (IDOR -> 404,
  not 403, so the id space is not enumerable), validated transitions, and
  the *correct* audit action (``project_status`` — it was logged as
  ``share_create`` before 2026-09-05).
* ``POST /share/{token}/approve`` — the token is the credential: unknown
  token 404, expired 410, unknown product 404, idempotent upsert keyed on
  (link, product), verdict/comment validation, per-IP rate limit.
* ``GET /share/{token}/approvals`` — expired link must be 410 here too (the
  original implementation skipped the check and leaked verdicts through a
  dead link).
* The designer sees approval tallies on the project (``approved_count`` /
  ``rejected_count``), which is the whole point of the loop.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.audit_log import ACTION_PROJECT_STATUS, AuditLog
from app.models.product import Product
from app.models.project import ClientApproval, ShareLink

QUIZ_BODY = {
    "styles": ["modern"], "color_palette": ["#D9A05B"],
    "room_width_cm": 400, "room_length_cm": 500,
    "budget_min_toman": 1_000_000, "budget_max_toman": 9_000_000,
    "materials": ["wood"], "patterns": ["solid"],
}


# ----------------------------------------------------------------- helpers

def _make_project(client, headers, name="پروژه"):
    resp = client.post("/api/v1/projects", headers=headers, json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _make_quiz(client, headers, project_id=None):
    body = dict(QUIZ_BODY)
    if project_id:
        body["project_id"] = project_id
    resp = client.post("/api/v1/quiz", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


def _share(client, headers, project_id, quiz_id, expires_days=30):
    resp = client.post(
        f"/api/v1/projects/{project_id}/share", headers=headers,
        json={"quiz_id": quiz_id, "expires_days": expires_days},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["token"]


def _any_product_id(db) -> str:
    pid = db.execute(select(Product.id).limit(1)).scalar_one_or_none()
    assert pid, "seeded catalogue is empty"
    return pid


def _expire(db, token: str) -> None:
    link = db.scalar(select(ShareLink).where(ShareLink.token == token))
    assert link is not None
    link.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()


@pytest.fixture()
def shared(client, db, designer):
    """A designer with one project, one quiz in it and a live share link."""
    h = designer["headers"]
    project = _make_project(client, h)
    quiz_id = _make_quiz(client, h, project["id"])
    token = _share(client, h, project["id"], quiz_id)
    return {
        "headers": h,
        "designer": designer,
        "project_id": project["id"],
        "quiz_id": quiz_id,
        "token": token,
        "product_id": _any_product_id(db),
    }


# ------------------------------------------------------- project status

def test_new_project_starts_as_draft(client, designer):
    project = _make_project(client, designer["headers"])
    assert project["status"] == "draft"
    assert project["approved_count"] == 0
    assert project["rejected_count"] == 0


@pytest.mark.parametrize("target", ["shared", "approved", "completed", "draft"])
def test_owner_can_set_every_valid_status(client, designer, target):
    h = designer["headers"]
    project = _make_project(client, h)
    resp = client.patch(
        f"/api/v1/projects/{project['id']}/status", headers=h, json={"status": target}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == target
    # And it is persisted — the whole reason status moved off localStorage.
    again = client.get(f"/api/v1/projects/{project['id']}", headers=h).json()["data"]
    assert again["status"] == target


def test_status_is_visible_in_the_project_list(client, designer):
    h = designer["headers"]
    project = _make_project(client, h)
    client.patch(f"/api/v1/projects/{project['id']}/status", headers=h, json={"status": "shared"})
    listed = client.get("/api/v1/projects", headers=h).json()["data"]
    assert {p["id"]: p["status"] for p in listed}[project["id"]] == "shared"


@pytest.mark.parametrize("bad", ["archived", "SHARED", "", "draft; drop table"])
def test_invalid_status_is_422(client, designer, bad):
    h = designer["headers"]
    project = _make_project(client, h)
    resp = client.patch(f"/api/v1/projects/{project['id']}/status", headers=h, json={"status": bad})
    assert resp.status_code == 422, resp.text


def test_status_body_rejects_unknown_fields(client, designer):
    h = designer["headers"]
    project = _make_project(client, h)
    resp = client.patch(
        f"/api/v1/projects/{project['id']}/status", headers=h,
        json={"status": "shared", "designer_id": "someone-else"},
    )
    assert resp.status_code == 422


def test_another_designer_cannot_change_status(client, make_user):
    owner, attacker = make_user("designer"), make_user("designer")
    project = _make_project(client, owner["headers"])
    resp = client.patch(
        f"/api/v1/projects/{project['id']}/status",
        headers=attacker["headers"], json={"status": "completed"},
    )
    # 404, not 403: an attacker must not learn that the id exists.
    assert resp.status_code == 404
    still = client.get(f"/api/v1/projects/{project['id']}", headers=owner["headers"]).json()["data"]
    assert still["status"] == "draft"


def test_homeowner_cannot_change_status(client, designer, homeowner):
    project = _make_project(client, designer["headers"])
    resp = client.patch(
        f"/api/v1/projects/{project['id']}/status",
        headers=homeowner["headers"], json={"status": "completed"},
    )
    assert resp.status_code == 403


def test_anonymous_cannot_change_status(client, designer):
    project = _make_project(client, designer["headers"])
    # Registration also set the httpOnly cookie pair on this TestClient (cookie
    # mode is the default). Drop them, or this is a CSRF-less cookie session
    # (403), not an anonymous caller (401).
    client.cookies.clear()
    resp = client.patch(f"/api/v1/projects/{project['id']}/status", json={"status": "completed"})
    assert resp.status_code == 401


def test_status_change_is_audited_with_its_own_action(client, db, designer):
    h = designer["headers"]
    project = _make_project(client, h)
    client.patch(f"/api/v1/projects/{project['id']}/status", headers=h, json={"status": "shared"})
    rows = db.scalars(
        select(AuditLog).where(
            AuditLog.action == ACTION_PROJECT_STATUS,
            AuditLog.user_id == designer["user"]["id"],
        )
    ).all()
    assert rows, "status change produced no project_status audit row"
    assert f"project={project['id']}" in rows[-1].detail
    assert "draft->shared" in rows[-1].detail


# ------------------------------------------------------ client approvals

def test_client_can_approve_without_an_account(client, shared):
    resp = client.post(
        f"/api/v1/share/{shared['token']}/approve",
        json={"product_id": shared["product_id"], "verdict": "approved", "comment": "عالیه"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {"product_id": shared["product_id"], "verdict": "approved"}


def test_approve_is_an_upsert_not_an_append(client, db, shared):
    url = f"/api/v1/share/{shared['token']}/approve"
    pid = shared["product_id"]
    client.post(url, json={"product_id": pid, "verdict": "approved"})
    client.post(url, json={"product_id": pid, "verdict": "rejected", "comment": "گران است"})
    client.post(url, json={"product_id": pid, "verdict": "rejected", "comment": "گران است"})

    link = db.scalar(select(ShareLink).where(ShareLink.token == shared["token"]))
    rows = db.scalars(select(ClientApproval).where(ClientApproval.share_link_id == link.id)).all()
    assert len(rows) == 1, "replaying the request must not create more rows"
    assert rows[0].verdict == "rejected"
    assert rows[0].comment == "گران است"


def test_returning_client_sees_previous_verdicts(client, shared):
    pid = shared["product_id"]
    client.post(f"/api/v1/share/{shared['token']}/approve",
                json={"product_id": pid, "verdict": "approved", "comment": "ok"})
    resp = client.get(f"/api/v1/share/{shared['token']}/approvals")
    assert resp.status_code == 200
    assert resp.json()["data"] == [{"product_id": pid, "verdict": "approved", "comment": "ok"}]


def test_designer_sees_approval_tallies_on_the_project(client, db, shared):
    pids = [r for r in db.execute(select(Product.id).limit(3)).scalars().all()]
    assert len(pids) == 3
    url = f"/api/v1/share/{shared['token']}/approve"
    client.post(url, json={"product_id": pids[0], "verdict": "approved"})
    client.post(url, json={"product_id": pids[1], "verdict": "approved"})
    client.post(url, json={"product_id": pids[2], "verdict": "rejected"})

    detail = client.get(
        f"/api/v1/projects/{shared['project_id']}", headers=shared["headers"]
    ).json()["data"]
    assert detail["approved_count"] == 2
    assert detail["rejected_count"] == 1

    listed = client.get("/api/v1/projects", headers=shared["headers"]).json()["data"]
    mine = next(p for p in listed if p["id"] == shared["project_id"])
    assert (mine["approved_count"], mine["rejected_count"]) == (2, 1)


@pytest.mark.parametrize("verdict", ["maybe", "APPROVED", "", "approved; --"])
def test_invalid_verdict_is_422(client, shared, verdict):
    resp = client.post(f"/api/v1/share/{shared['token']}/approve",
                       json={"product_id": shared["product_id"], "verdict": verdict})
    assert resp.status_code == 422


def test_comment_is_sanitised_and_bounded(client, shared):
    url = f"/api/v1/share/{shared['token']}/approve"
    pid = shared["product_id"]
    xss = '<img src=x onerror="alert(1)">nice'
    resp = client.post(url, json={"product_id": pid, "verdict": "approved", "comment": xss})
    assert resp.status_code == 200, resp.text
    stored = client.get(f"/api/v1/share/{shared['token']}/approvals").json()["data"][0]["comment"]
    assert "<img" not in stored and "onerror" not in stored

    too_long = "x" * 1001
    resp = client.post(url, json={"product_id": pid, "verdict": "approved", "comment": too_long})
    assert resp.status_code == 422


def test_unknown_product_is_404(client, shared):
    resp = client.post(f"/api/v1/share/{shared['token']}/approve",
                       json={"product_id": "does-not-exist-000", "verdict": "approved"})
    assert resp.status_code == 404


def test_unknown_token_is_404_for_both_endpoints(client):
    assert client.post("/api/v1/share/nope-nope-nope/approve",
                       json={"product_id": "x", "verdict": "approved"}).status_code == 404
    assert client.get("/api/v1/share/nope-nope-nope/approvals").status_code == 404


def test_oversized_token_is_404_not_500(client):
    token = "a" * 129
    assert client.post(f"/api/v1/share/{token}/approve",
                       json={"product_id": "x", "verdict": "approved"}).status_code == 404
    assert client.get(f"/api/v1/share/{token}/approvals").status_code == 404


def test_expired_link_refuses_approve_and_approvals(client, db, shared):
    pid = shared["product_id"]
    client.post(f"/api/v1/share/{shared['token']}/approve",
                json={"product_id": pid, "verdict": "approved"})
    _expire(db, shared["token"])

    resp = client.post(f"/api/v1/share/{shared['token']}/approve",
                       json={"product_id": pid, "verdict": "rejected"})
    assert resp.status_code == 410

    # Regression: the list endpoint used to skip the expiry check, so a dead
    # link still disclosed the client's decisions to anyone holding the URL.
    assert client.get(f"/api/v1/share/{shared['token']}/approvals").status_code == 410
    # And the public view agrees.
    assert client.get(f"/api/v1/share/{shared['token']}").status_code == 410


def test_approve_is_rate_limited_per_ip(client, shared, reset_settings):
    reset_settings(SHARE_RATE_LIMIT_PER_MINUTE=3)
    url = f"/api/v1/share/{shared['token']}/approve"
    body = {"product_id": shared["product_id"], "verdict": "approved"}
    codes = [client.post(url, json=body).status_code for _ in range(4)]
    assert codes[:3] == [200, 200, 200], codes
    assert codes[3] == 429, codes
    # The GET shares the same bucket — a leaked link cannot be polled either.
    assert client.get(f"/api/v1/share/{shared['token']}/approvals").status_code == 429


def test_approvals_do_not_leak_across_links(client, db, make_user):
    """Two designers, two links: verdicts on one never show up on the other."""
    a, b = make_user("designer"), make_user("designer")
    pid = _any_product_id(db)
    tokens = []
    for u in (a, b):
        p = _make_project(client, u["headers"])
        q = _make_quiz(client, u["headers"], p["id"])
        tokens.append(_share(client, u["headers"], p["id"], q))

    client.post(f"/api/v1/share/{tokens[0]}/approve", json={"product_id": pid, "verdict": "approved"})
    assert client.get(f"/api/v1/share/{tokens[1]}/approvals").json()["data"] == []
