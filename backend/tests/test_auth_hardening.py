"""Stage 03 · authentication hardening (probe A-*, K-*, R-*, T-01).

Covers: brute-force lockout, registration/login throttling with `Retry-After`,
password policy, user-enumeration timing, cookie flags, CSRF double-submit,
refresh rotation/revocation and JWT algorithm confusion.
"""
from __future__ import annotations

import time
import uuid

import pytest

from app.core.cookies import ACCESS_COOKIE, CSRF_COOKIE, CSRF_HEADER, REFRESH_COOKIE

LOGIN = "/api/v1/auth/login"
REGISTER = "/api/v1/auth/register"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"

#: The seeded designer — `/projects` is designer-only, and it is the most
#: convenient authenticated state-changing endpoint to prove CSRF with.
DESIGNER = {"email": "designer@smartdecor.dev", "password": "Design123!"}


def _email() -> str:
    return f"auth-{uuid.uuid4().hex[:10]}@example.com"


# ------------------------------------------------------------ brute force (T-04)

def test_wrong_password_locks_the_account_out(client, demo_user, reset_settings):
    """Five wrong passwords must stop the sixth attempt, right password or not."""
    reset_settings(LOGIN_RATE_LIMIT_PER_MINUTE=1000)
    statuses = []
    for _ in range(6):
        resp = client.post(LOGIN, json={"email": demo_user["email"],
                                        "password": "definitely-wrong"})
        statuses.append(resp.status_code)
    assert statuses[0] == 401
    assert 429 in statuses, statuses

    # The lockout is not bypassed by finally supplying the correct password.
    blocked = client.post(LOGIN, json=demo_user)
    assert blocked.status_code == 429, blocked.text
    assert blocked.headers.get("Retry-After"), "a lockout must say when to retry"
    assert int(blocked.headers["Retry-After"]) > 0


def test_lockout_is_scoped_to_the_targeted_account(client, demo_user,
                                                   reset_settings):
    """One victim's lockout must not become a DoS on everyone else."""
    reset_settings(LOGIN_RATE_LIMIT_PER_MINUTE=1000)
    for _ in range(6):
        client.post(LOGIN, json={"email": demo_user["email"], "password": "nope"})
    other = client.post(LOGIN, json={"email": "admin@smartdecor.dev",
                                     "password": "Admin123!"})
    assert other.status_code == 200, other.text


def test_successful_login_resets_the_failure_counter(client, demo_user,
                                                     reset_settings):
    reset_settings(LOGIN_RATE_LIMIT_PER_MINUTE=1000)
    for _ in range(3):
        client.post(LOGIN, json={"email": demo_user["email"], "password": "nope"})
    assert client.post(LOGIN, json=demo_user).status_code == 200
    for _ in range(3):
        resp = client.post(LOGIN, json={"email": demo_user["email"],
                                        "password": "nope"})
        assert resp.status_code == 401, "counter was not reset by the success"


def test_login_failures_do_not_reveal_whether_the_account_exists(client,
                                                                 demo_user):
    missing = client.post(LOGIN, json={"email": "nobody-here@example.com",
                                       "password": "whatever!"})
    wrong = client.post(LOGIN, json={"email": demo_user["email"],
                                     "password": "whatever!"})
    assert missing.status_code == wrong.status_code == 401
    assert missing.json()["error"] == wrong.json()["error"]


def test_login_timing_does_not_leak_account_existence(client, demo_user,
                                                      reset_settings):
    """T-01: baseline was 268 ms vs 9 ms — a 30x user-enumeration oracle."""
    reset_settings(LOGIN_RATE_LIMIT_PER_MINUTE=10_000)

    def timed(email: str) -> float:
        samples = []
        for _ in range(3):
            start = time.perf_counter()
            client.post(LOGIN, json={"email": email, "password": "Wrong123!x"})
            samples.append(time.perf_counter() - start)
        return sorted(samples)[1]  # median

    known = timed(demo_user["email"])
    unknown = timed(f"ghost-{uuid.uuid4().hex[:8]}@example.com")
    ratio = max(known, unknown) / max(min(known, unknown), 1e-6)
    assert ratio < 3.0, f"timing oracle: known={known:.4f}s unknown={unknown:.4f}s"


# ------------------------------------------------------- throttling (T-05/T-06)

def test_login_is_rate_limited_per_ip_with_retry_after(client, reset_settings):
    reset_settings(LOGIN_RATE_LIMIT_PER_MINUTE=3)
    last = None
    for _ in range(6):
        last = client.post(LOGIN, json={"email": _email(), "password": "Wrong123!x"})
    assert last.status_code == 429
    assert last.headers.get("Retry-After")


def test_registration_is_rate_limited_with_retry_after(client):
    body = {"password": "Str0ngTestPassphrase!", "full_name": "Flood"}
    codes = [
        client.post(REGISTER, json={**body, "email": _email()}).status_code
        for _ in range(6)
    ]
    assert codes.count(201) <= 3, codes
    assert 429 in codes, codes
    blocked = client.post(REGISTER, json={**body, "email": _email()})
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After")


def test_rate_limited_responses_still_carry_security_headers(client,
                                                             reset_settings):
    """Error responses must not be a hole in the header policy."""
    reset_settings(LOGIN_RATE_LIMIT_PER_MINUTE=1)
    for _ in range(3):
        resp = client.post(LOGIN, json={"email": _email(), "password": "Wrong123!x"})
    assert resp.status_code == 429
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert "Content-Security-Policy" in resp.headers


# ---------------------------------------------------------- password policy

@pytest.mark.parametrize("password", [
    "short1!",            # too short
    "password",           # no digit/upper/symbol, and a banned password
    "Password1",          # no symbol
    "abcdefghijklmn",     # sequential run
    "aaaaaaaaaaaa",       # one repeated character
    "Password123!" + "x" * 200,   # over the bcrypt 72-byte limit
])
def test_weak_passwords_are_rejected_at_registration(client, password):
    resp = client.post(REGISTER, json={
        "email": _email(), "password": password, "full_name": "Weak"})
    assert resp.status_code == 422, resp.text


def test_a_reasonable_password_is_still_accepted(client):
    resp = client.post(REGISTER, json={
        "email": _email(), "password": "Password123!", "full_name": "Fine"})
    assert resp.status_code == 201, resp.text


def test_role_escalation_at_registration_is_rejected(client):
    """Self-registering as an admin must never work."""
    resp = client.post(REGISTER, json={
        "email": _email(), "password": "Str0ngTestPassphrase!",
        "full_name": "Wannabe", "role": "admin"})
    assert resp.status_code == 422, resp.text


def test_unknown_fields_are_rejected_at_registration(client):
    resp = client.post(REGISTER, json={
        "email": _email(), "password": "Str0ngTestPassphrase!",
        "full_name": "Extra", "is_admin": True, "hashed_password": "x"})
    assert resp.status_code == 422, resp.text


def test_password_is_never_echoed_back(client):
    resp = client.post(REGISTER, json={
        "email": _email(), "password": "Str0ngTestPassphrase!", "full_name": "N"})
    assert resp.status_code == 201
    assert "Str0ngTestPassphrase!" not in resp.text
    assert "hashed_password" not in resp.text


# -------------------------------------------------------------- cookies / CSRF

def test_login_sets_hardened_cookies(client, demo_user, reset_settings):
    reset_settings(USE_COOKIE_AUTH=True)
    resp = client.post(LOGIN, json=demo_user)
    assert resp.status_code == 200, resp.text
    raw = resp.headers.get_list("set-cookie")
    access = next(c for c in raw if c.startswith(f"{ACCESS_COOKIE}="))
    refresh = next(c for c in raw if c.startswith(f"{REFRESH_COOKIE}="))
    csrf = next(c for c in raw if c.startswith(f"{CSRF_COOKIE}="))
    for cookie in (access, refresh):
        assert "HttpOnly" in cookie, cookie
        assert "SameSite" in cookie, cookie
        assert "Path=/" in cookie, cookie
    # The CSRF cookie is readable by design — double-submit needs it.
    assert "HttpOnly" not in csrf


def test_cookie_session_can_call_the_api_without_a_bearer_token(client, demo_user,
                                                                reset_settings):
    reset_settings(USE_COOKIE_AUTH=True)
    assert client.post(LOGIN, json=demo_user).status_code == 200
    resp = client.get(ME)
    assert resp.status_code == 200, resp.text


def test_state_change_from_a_cookie_session_requires_the_csrf_header(
        client, reset_settings):
    reset_settings(USE_COOKIE_AUTH=True)
    assert client.post(LOGIN, json=DESIGNER).status_code == 200

    forged = client.post("/api/v1/projects", json={"name": "csrf-probe"})
    assert forged.status_code == 403, forged.text

    token = client.cookies.get(CSRF_COOKIE)
    allowed = client.post("/api/v1/projects", headers={CSRF_HEADER: token},
                          json={"name": "legit-project"})
    assert allowed.status_code in (200, 201), allowed.text


def test_a_wrong_csrf_token_is_not_accepted(client, reset_settings):
    reset_settings(USE_COOKIE_AUTH=True)
    assert client.post(LOGIN, json=DESIGNER).status_code == 200
    resp = client.post("/api/v1/projects", headers={CSRF_HEADER: "not-the-token"},
                       json={"name": "x"})
    assert resp.status_code == 403


def test_cookie_refresh_requires_csrf(client, demo_user, reset_settings):
    """T-09: /refresh mints new credentials — the top CSRF target."""
    reset_settings(USE_COOKIE_AUTH=True)
    assert client.post(LOGIN, json=demo_user).status_code == 200
    assert client.post(REFRESH).status_code == 403
    token = client.cookies.get(CSRF_COOKIE)
    assert client.post(REFRESH, headers={CSRF_HEADER: token}).status_code == 200


def test_body_token_refresh_does_not_need_csrf(client, demo_user):
    """A token the attacker cannot read is not ambient authority."""
    login = client.post(LOGIN, json=demo_user)
    refresh_token = login.json()["data"]["refresh_token"]
    fresh = client.__class__(client.app)  # a clean client: no cookies at all
    resp = fresh.post(REFRESH, json={"refresh_token": refresh_token})
    assert resp.status_code == 200, resp.text


def test_logout_clears_the_cookies(client, demo_user, reset_settings):
    reset_settings(USE_COOKIE_AUTH=True)
    assert client.post(LOGIN, json=demo_user).status_code == 200
    token = client.cookies.get(CSRF_COOKIE)
    resp = client.post(LOGOUT, headers={CSRF_HEADER: token})
    assert resp.status_code == 200, resp.text
    cleared = " ".join(resp.headers.get_list("set-cookie"))
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        assert name in cleared


# ------------------------------------------------------------- token lifecycle

def test_refresh_rotates_and_revokes_the_old_token(client, demo_user):
    login = client.post(LOGIN, json=demo_user).json()["data"]
    first = login["refresh_token"]
    rotated = client.post(REFRESH, json={"refresh_token": first})
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["data"]["refresh_token"] != first
    replay = client.post(REFRESH, json={"refresh_token": first})
    assert replay.status_code == 401, "a used refresh token must be revoked"


def test_access_token_is_not_accepted_as_a_refresh_token(client, demo_user):
    access = client.post(LOGIN, json=demo_user).json()["data"]["access_token"]
    resp = client.post(REFRESH, json={"refresh_token": access})
    assert resp.status_code == 401


def test_logout_revokes_the_refresh_token(client, demo_user):
    data = client.post(LOGIN, json=demo_user).json()["data"]
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    assert client.post(LOGOUT, headers=headers,
                       json={"refresh_token": data["refresh_token"]}).status_code == 200
    replay = client.post(REFRESH, json={"refresh_token": data["refresh_token"]})
    assert replay.status_code == 401


# -------------------------------------------------------------- JWT integrity

def test_alg_none_token_is_rejected(client, demo_user):
    """Algorithm-confusion: an unsigned token must never authenticate."""
    import base64
    import json

    def b64(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    forged = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64({'sub': 'x', 'type': 'access'})}."
    resp = client.get(ME, headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 401


def test_tampered_signature_is_rejected(client, demo_user):
    token = client.post(LOGIN, json=demo_user).json()["data"]["access_token"]
    head, payload, sig = token.split(".")
    tampered = f"{head}.{payload}.{'A' * len(sig)}"
    assert client.get(ME, headers={"Authorization": f"Bearer {tampered}"}).status_code == 401


def test_garbage_authorization_header_is_401_not_500(client):
    for value in ("Bearer", "Bearer ", "Bearer ...", "Basic YWRtaW46YWRtaW4=",
                  "Bearer " + "A" * 5000):
        resp = client.get(ME, headers={"Authorization": value})
        assert resp.status_code == 401, f"{value!r} -> {resp.status_code}"


def test_disabled_account_cannot_use_an_existing_token(client, db, make_user):
    from app.models.user import User

    actor = make_user()
    user = db.get(User, actor["user"]["id"])
    user.is_active = False
    db.commit()
    try:
        resp = client.get(ME, headers=actor["headers"])
        assert resp.status_code in (401, 403), resp.text
    finally:
        user.is_active = True
        db.commit()
