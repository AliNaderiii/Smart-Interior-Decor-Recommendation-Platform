"""Auth + security tests: register/login/refresh/logout, bcrypt, GDPR delete."""
from __future__ import annotations

import uuid


def _email() -> str:
    return f"auth-{uuid.uuid4().hex[:8]}@example.com"


def test_register_returns_tokens_and_user(client):
    resp = client.post("/api/v1/auth/register", json={
        "email": _email(), "password": "Password123!", "full_name": "Reg Test",
    })
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["access_token"] and data["refresh_token"]
    assert data["user"]["role"] == "homeowner"
    assert data["user"]["subscription_active"] is False


def test_register_duplicate_email_409(client):
    email = _email()
    body = {"email": email, "password": "Password123!"}
    assert client.post("/api/v1/auth/register", json=body).status_code == 201
    assert client.post("/api/v1/auth/register", json=body).status_code == 409


def test_password_is_bcrypt_hashed(client, db):
    from sqlalchemy import select

    from app.models.user import User

    email = _email()
    client.post("/api/v1/auth/register", json={"email": email, "password": "Password123!"})
    user = db.scalar(select(User).where(User.email == email))
    assert user.hashed_password.startswith("$2b$")
    assert "Password123!" not in user.hashed_password


def test_login_wrong_password_401(client):
    email = _email()
    client.post("/api/v1/auth/register", json={"email": email, "password": "Password123!"})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-pass"})
    assert resp.status_code == 401


def test_login_and_me(client):
    email = _email()
    client.post("/api/v1/auth/register", json={"email": email, "password": "Password123!"})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    assert login.status_code == 200
    token = login.json()["data"]["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["data"]["email"] == email


def test_refresh_rotates_and_blacklists_old_token(client):
    email = _email()
    reg = client.post("/api/v1/auth/register", json={"email": email, "password": "Password123!"})
    refresh_token = reg.json()["data"]["refresh_token"]

    first = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert first.status_code == 200
    # Re-using the rotated (blacklisted) token must fail.
    second = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert second.status_code == 401


def test_logout_blacklists_refresh_token(client):
    email = _email()
    reg = client.post("/api/v1/auth/register", json={"email": email, "password": "Password123!"})
    data = reg.json()["data"]
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    out = client.post("/api/v1/auth/logout", headers=headers,
                      json={"refresh_token": data["refresh_token"]})
    assert out.status_code == 200
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert resp.status_code == 401


def test_protected_route_requires_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me",
                      headers={"Authorization": "Bearer not-a-token"}).status_code == 401


def test_admin_routes_forbidden_for_homeowner(client, auth_headers):
    headers, _ = auth_headers
    assert client.get("/api/v1/admin/users", headers=headers).status_code == 403
    assert client.get("/api/v1/products", headers=headers).status_code == 403


def test_gdpr_delete_removes_everything(client, db):
    from sqlalchemy import select

    from app.models.moodboard import Moodboard
    from app.models.quiz import StyleQuiz
    from app.models.user import User

    email = _email()
    reg = client.post("/api/v1/auth/register", json={"email": email, "password": "Password123!"})
    data = reg.json()["data"]
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    uid = data["user"]["id"]

    client.post("/api/v1/quiz", headers=headers, json={
        "styles": ["modern"], "color_palette": ["#FFFFFF"],
        "room_width_cm": 400, "room_length_cm": 500,
        "budget_min_toman": 1_000_000, "budget_max_toman": 90_000_000,
        "materials": ["wood"], "patterns": [],
    })
    client.post("/api/v1/moodboards", headers=headers, json={"title": "b", "items": []})

    resp = client.delete("/api/v1/users/me", headers=headers)
    assert resp.status_code == 200

    assert db.scalar(select(User).where(User.id == uid)) is None
    assert db.scalar(select(StyleQuiz).where(StyleQuiz.user_id == uid)) is None
    assert db.scalar(select(Moodboard).where(Moodboard.user_id == uid)) is None


def test_recommend_endpoint_paywall_for_free_user(client, auth_headers):
    headers, _ = auth_headers
    resp = client.post("/api/v1/recommend", headers=headers, json={
        "styles": ["modern"], "color_palette": ["#2E2E2E"],
        "room_width_cm": 400, "room_length_cm": 500,
        "budget_min_toman": 1_000_000, "budget_max_toman": 150_000_000,
        "materials": ["wood"], "patterns": [],
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["is_pro"] is False
    for items in data["categories"].values():
        assert "final_score" in items[0]  # first item full
        for locked in items[1:]:
            assert locked.get("locked") is True
            assert "price_toman" not in locked  # teaser only


def test_payment_flow_activates_subscription(client, auth_headers):
    headers, _ = auth_headers
    req = client.post("/api/v1/payment/request", headers=headers)
    assert req.status_code == 201
    authority = req.json()["data"]["authority"]

    verify = client.post("/api/v1/payment/verify", headers=headers,
                         json={"authority": authority, "status": "OK"})
    assert verify.status_code == 200
    assert verify.json()["data"]["status"] == "paid"

    sub = client.get("/api/v1/subscriptions/me", headers=headers)
    assert sub.json()["data"]["is_active"] is True

    rec = client.post("/api/v1/recommend", headers=headers, json={
        "styles": ["modern"], "color_palette": ["#2E2E2E"],
        "room_width_cm": 400, "room_length_cm": 500,
        "budget_min_toman": 1_000_000, "budget_max_toman": 150_000_000,
        "materials": ["wood"], "patterns": [],
    })
    data = rec.json()["data"]
    assert data["is_pro"] is True
    for items in data["categories"].values():
        assert all("final_score" in i for i in items)


def test_designer_project_and_share_flow(client):
    login = client.post("/api/v1/auth/login", json={
        "email": "designer@smartdecor.dev", "password": "Design123!",
    })
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}

    proj = client.post("/api/v1/projects", headers=headers,
                       json={"name": "Villa Lavasan", "client_name": "Mr. Ahmadi"})
    assert proj.status_code == 201
    project_id = proj.json()["data"]["id"]

    quiz = client.post("/api/v1/quiz", headers=headers, json={
        "styles": ["classic"], "color_palette": ["#6D4C33"],
        "room_width_cm": 600, "room_length_cm": 800,
        "budget_min_toman": 20_000_000, "budget_max_toman": 300_000_000,
        "materials": ["wood"], "patterns": ["persian"],
        "project_id": project_id, "client_name": "Mr. Ahmadi",
    })
    assert quiz.status_code == 201
    quiz_id = quiz.json()["data"]["id"]

    share = client.post(f"/api/v1/projects/{project_id}/share", headers=headers,
                        json={"quiz_id": quiz_id})
    assert share.status_code == 201
    token = share.json()["data"]["token"]

    public = client.get(f"/api/v1/share/{token}")
    assert public.status_code == 200
    assert public.json()["data"]["categories"]
