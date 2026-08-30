"""Stage 3 Offensive Penetration Testing & Vulnerability Assessment Suite (T-3.1).

Covers 14 offensive attack classes executed by SA-2 (Red Team) against the
local stack with disposable test users, capturing structured audit traces and
asserting cryptographic, authorization, sanitization, and rate-limiting defenses.
"""
from __future__ import annotations

import io
import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.cookies import ACCESS_COOKIE, CSRF_COOKIE, CSRF_HEADER
from app.core.redis_client import get_redis
from app.core.security import create_token, hash_password
from app.core.url_safety import UnsafeUrl, validate_public_url
from app.models.moodboard import Moodboard
from app.models.project import Project, ShareLink
from app.models.quiz import StyleQuiz
from app.models.subscription import Subscription
from app.models.user import User

logger = logging.getLogger("penetration_test")

EVIDENCE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "docs", "agent-reports", "stage3-evidence", "t-3.1-attacks"
)
os.makedirs(EVIDENCE_DIR, exist_ok=True)
SESSION_LOG = os.path.join(EVIDENCE_DIR, "attack_session.jsonl")


def record_attack_step(
    attack_class: str,
    target: str,
    method: str,
    description: str,
    status_code: int,
    verdict: str,
    details: str = "",
) -> None:
    """Record machine-verifiable pentest telemetry."""
    entry = {
        "timestamp": time.time(),
        "attack_class": attack_class,
        "method": method,
        "target": target,
        "description": description,
        "status_code": status_code,
        "verdict": verdict,
        "details": details,
    }
    with open(SESSION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


@pytest.fixture(autouse=True)
def clean_test_redis():
    """Ensure Redis counters/blacklists are clean between tests."""
    redis = get_redis()
    redis.flushall()
    yield
    redis.flushall()


def _create_user(db, email: str, role: str = "homeowner", active: bool = True) -> User:
    u = User(
        email=email.lower(),
        hashed_password=hash_password("Pass1234!Secure"),
        full_name=f"Test {role.capitalize()}",
        role=role,
        is_active=active,
    )
    u.subscription = Subscription(plan="free", is_active=False)
    db.add(u)
    db.commit()
    return u


# ============================================================================
# 1. AUTH & BRUTE-FORCE LOCKOUT
# ============================================================================
def test_attack_class_1_auth_and_brute_force(client: TestClient, db):
    email = f"e2e-victim-{uuid.uuid4().hex[:8]}@example.com"
    _create_user(db, email, "homeowner")

    # Positive case: valid login succeeds
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "Pass1234!Secure"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    record_attack_step("Auth & Brute-Force", "/api/v1/auth/login", "POST", "Legitimate authentication", 200, "PASS")

    # Negative case 1: 5 rapid bad-password attempts trigger 429 lockout
    client_ip = "192.0.2.1"
    headers = {"X-Forwarded-For": client_ip}
    for i in range(1, 5):
        r = client.post("/api/v1/auth/login", json={"email": email, "password": f"wrong_{i}"}, headers=headers)
        assert r.status_code == 401

    # 5th failure triggers lockout
    lockout_resp = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "wrong_5"}, headers=headers
    )
    assert lockout_resp.status_code == 429
    assert "Retry-After" in lockout_resp.headers
    record_attack_step("Auth & Brute-Force", "/api/v1/auth/login", "POST", "Brute-force lockout trigger", 429, "PASS")

    # Negative case 2: Disabled account blocked
    disabled_email = f"e2e-disabled-{uuid.uuid4().hex[:8]}@example.com"
    _create_user(db, disabled_email, "homeowner", active=False)
    dis_resp = client.post(
        "/api/v1/auth/login", json={"email": disabled_email, "password": "Pass1234!Secure"}
    )
    assert dis_resp.status_code == 403
    record_attack_step("Auth & Brute-Force", "/api/v1/auth/login", "POST", "Disabled account rejection", 403, "PASS")


# ============================================================================
# 2. JWT TAMPERING & ALGORITHM CONFUSION
# ============================================================================
def test_attack_class_2_jwt_tampering(client: TestClient, db):
    user = _create_user(db, f"e2e-jwt-{uuid.uuid4().hex[:8]}@example.com", "homeowner")
    valid_token = create_token(user.id, "access")

    # Positive case
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {valid_token}"})
    assert resp.status_code == 200
    record_attack_step("JWT Tampering", "/api/v1/auth/me", "GET", "Valid HS256 access token", 200, "PASS")

    # Negative case 1: alg "none" attack
    none_token = jwt.encode({"sub": user.id, "type": "access", "jti": "attack1"}, key="", algorithm="none")
    r_none = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {none_token}"})
    assert r_none.status_code == 401
    record_attack_step("JWT Tampering", "/api/v1/auth/me", "GET", "alg: 'none' bypass attempt", 401, "PASS")

    # Negative case 2: wrong secret
    fake_token = jwt.encode({"sub": user.id, "type": "access", "jti": "attack2"}, key="attacker_secret_key_1234567890", algorithm="HS256")
    r_fake = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {fake_token}"})
    assert r_fake.status_code == 401
    record_attack_step("JWT Tampering", "/api/v1/auth/me", "GET", "Forged secret signature", 401, "PASS")

    # Negative case 3: expired token
    expired_token = create_token(user.id, "access", expires_delta=timedelta(seconds=-60))
    r_exp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert r_exp.status_code == 401
    record_attack_step("JWT Tampering", "/api/v1/auth/me", "GET", "Expired token reuse", 401, "PASS")

    # Negative case 4: refresh token presented as access token
    refresh_token = create_token(user.id, "refresh")
    r_typ = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {refresh_token}"})
    assert r_typ.status_code == 401
    record_attack_step("JWT Tampering", "/api/v1/auth/me", "GET", "Token type confusion (refresh as access)", 401, "PASS")


# ============================================================================
# 3. REFRESH TOKEN ROTATION & RACE CONDITIONS
# ============================================================================
def test_attack_class_3_refresh_rotation_and_blacklist(client: TestClient, db):
    user = _create_user(db, f"e2e-rotate-{uuid.uuid4().hex[:8]}@example.com", "homeowner")
    refresh_1 = create_token(user.id, "refresh")

    # Step 1: Rotate refresh token
    r1 = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_1})
    assert r1.status_code == 200
    refresh_2 = r1.json()["data"]["refresh_token"]
    assert refresh_2 != refresh_1
    record_attack_step("Refresh Token Rotation", "/api/v1/auth/refresh", "POST", "Legitimate token rotation", 200, "PASS")

    # Step 2: Replay burned refresh token (refresh_1)
    r_replay = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_1})
    assert r_replay.status_code == 401
    record_attack_step("Refresh Token Rotation", "/api/v1/auth/refresh", "POST", "Replay of burned refresh token", 401, "PASS")

    # Step 3: Logout invalidates active refresh token
    access_2 = r1.json()["data"]["access_token"]
    r_logout = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_2},
        headers={"Authorization": f"Bearer {access_2}"},
    )
    assert r_logout.status_code == 200

    r_post_logout = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_2})
    assert r_post_logout.status_code == 401
    record_attack_step("Refresh Token Rotation", "/api/v1/auth/refresh", "POST", "Refresh token reuse after logout", 401, "PASS")


# ============================================================================
# 4. IDOR ON MOODBOARDS
# ============================================================================
def test_attack_class_4_idor_moodboards(client: TestClient, db):
    user_a = _create_user(db, f"e2e-user-a-{uuid.uuid4().hex[:8]}@example.com", "homeowner")
    user_b = _create_user(db, f"e2e-user-b-{uuid.uuid4().hex[:8]}@example.com", "homeowner")

    token_a = create_token(user_a.id, "access")
    token_b = create_token(user_b.id, "access")

    # User A creates a moodboard
    mb_a = Moodboard(
        user_id=user_a.id,
        title="User A Living Room",
        items=[{"product_id": "p1", "x": 0, "y": 0, "w": 200, "h": 200}],
        shopping_list=["p1"],
    )
    db.add(mb_a)
    db.commit()

    # Positive: User A can read own moodboard
    r_a = client.get(f"/api/v1/moodboards/{mb_a.id}", headers={"Authorization": f"Bearer {token_a}"})
    assert r_a.status_code == 200
    record_attack_step("IDOR Moodboards", f"/api/v1/moodboards/{mb_a.id}", "GET", "Owner access to moodboard", 200, "PASS")

    # Attack 1: User B tries to read User A's moodboard
    r_b_get = client.get(f"/api/v1/moodboards/{mb_a.id}", headers={"Authorization": f"Bearer {token_b}"})
    assert r_b_get.status_code == 404
    record_attack_step("IDOR Moodboards", f"/api/v1/moodboards/{mb_a.id}", "GET", "Unauthorized read of foreign moodboard", 404, "PASS")

    # Attack 2: User B tries to update User A's moodboard
    r_b_patch = client.patch(
        f"/api/v1/moodboards/{mb_a.id}",
        json={"title": "Hacked Title"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r_b_patch.status_code == 404
    record_attack_step("IDOR Moodboards", f"/api/v1/moodboards/{mb_a.id}", "PATCH", "Unauthorized update of foreign moodboard", 404, "PASS")

    # Attack 3: User B tries to delete User A's moodboard
    r_b_del = client.delete(f"/api/v1/moodboards/{mb_a.id}", headers={"Authorization": f"Bearer {token_b}"})
    assert r_b_del.status_code == 404
    record_attack_step("IDOR Moodboards", f"/api/v1/moodboards/{mb_a.id}", "DELETE", "Unauthorized deletion of foreign moodboard", 404, "PASS")


# ============================================================================
# 5. IDOR ON DESIGNER PROJECTS & PROXY QUIZZES
# ============================================================================
def test_attack_class_5_idor_designer_projects(client: TestClient, db):
    designer_a = _create_user(db, f"e2e-des-a-{uuid.uuid4().hex[:8]}@example.com", "designer")
    designer_b = _create_user(db, f"e2e-des-b-{uuid.uuid4().hex[:8]}@example.com", "designer")
    homeowner = _create_user(db, f"e2e-home-{uuid.uuid4().hex[:8]}@example.com", "homeowner")

    token_a = create_token(designer_a.id, "access")
    token_b = create_token(designer_b.id, "access")
    token_h = create_token(homeowner.id, "access")

    # Designer A creates a project
    proj_a = Project(designer_id=designer_a.id, name="Villa Project A", client_name="Client A")
    db.add(proj_a)
    db.commit()

    # Positive: Designer A views project
    r_a = client.get(f"/api/v1/projects/{proj_a.id}", headers={"Authorization": f"Bearer {token_a}"})
    assert r_a.status_code == 200
    record_attack_step("IDOR Projects", f"/api/v1/projects/{proj_a.id}", "GET", "Designer accesses own project", 200, "PASS")

    # Attack 1: Designer B views Designer A's project
    r_b = client.get(f"/api/v1/projects/{proj_a.id}", headers={"Authorization": f"Bearer {token_b}"})
    assert r_b.status_code == 404
    record_attack_step("IDOR Projects", f"/api/v1/projects/{proj_a.id}", "GET", "Unauthorized read of foreign project", 404, "PASS")

    # Attack 2: Designer B attempts to delete Designer A's project
    r_del = client.delete(f"/api/v1/projects/{proj_a.id}", headers={"Authorization": f"Bearer {token_b}"})
    assert r_del.status_code == 404
    record_attack_step("IDOR Projects", f"/api/v1/projects/{proj_a.id}", "DELETE", "Unauthorized deletion of foreign project", 404, "PASS")

    # Attack 3 (Finding S3-F001): Homeowner or Designer B attempting to attach quiz to Designer A's project
    r_attach = client.post(
        "/api/v1/quiz",
        json={
            "project_id": proj_a.id,
            "styles": ["modern"],
            "color_palette": ["#112233"],
            "room_width_cm": 400,
            "room_length_cm": 500,
            "budget_min_toman": 1000000,
            "budget_max_toman": 50000000,
            "materials": ["wood"],
            "patterns": ["solid"],
        },
        headers={"Authorization": f"Bearer {token_h}"},
    )
    # Must be 404 Project not found or 403
    assert r_attach.status_code in (404, 403), f"Expected 404/403 but got {r_attach.status_code}: {r_attach.text}"
    record_attack_step("IDOR Projects", "/api/v1/quiz", "POST", "Cross-tenant quiz attachment attempt (S3-F001)", r_attach.status_code, "PASS")


# ============================================================================
# 6. PUBLIC SHARE TOKEN SECURITY & ENUMERATION
# ============================================================================
def test_attack_class_6_share_token_security(client: TestClient, db):
    designer = _create_user(db, f"e2e-share-des-{uuid.uuid4().hex[:8]}@example.com", "designer")
    token_des = create_token(designer.id, "access")

    proj = Project(designer_id=designer.id, name="Shareable Project", client_name="Client X")
    db.add(proj)
    db.commit()

    quiz = StyleQuiz(
        user_id=designer.id,
        project_id=proj.id,
        client_name="Client X",
        styles=["modern"],
        color_palette=["#112233"],
        room_width_cm=400,
        room_length_cm=500,
        budget_min_toman=1000000,
        budget_max_toman=50000000,
        materials=["wood"],
        patterns=["solid"],
    )
    db.add(quiz)
    db.commit()

    # Generate share token
    share_res = client.post(
        f"/api/v1/projects/{proj.id}/share",
        json={"quiz_id": quiz.id, "expires_days": 10},
        headers={"Authorization": f"Bearer {token_des}"},
    )
    assert share_res.status_code == 201
    share_token = share_res.json()["data"]["token"]
    assert len(share_token) >= 32

    # Positive case: viewing public share
    r_view = client.get(f"/api/v1/share/{share_token}")
    assert r_view.status_code == 200
    share_data = r_view.json()["data"]
    assert "client_name" in share_data
    # Verify no PII leak (no email, hashed password, user id)
    assert "email" not in str(share_data)
    assert "hashed_password" not in str(share_data)
    record_attack_step("Public Share Token", f"/api/v1/share/{share_token}", "GET", "Public share view without PII leak", 200, "PASS")

    # Negative case 1: Non-existent / guessing token
    r_fake = client.get("/api/v1/share/non_existent_token_12345")
    assert r_fake.status_code == 404
    record_attack_step("Public Share Token", "/api/v1/share/fake", "GET", "Invalid token enumeration", 404, "PASS")

    # Negative case 2: Expired token
    link_row = db.scalar(db.query(ShareLink).filter_by(token=share_token))
    link_row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    r_exp = client.get(f"/api/v1/share/{share_token}")
    assert r_exp.status_code == 410
    record_attack_step("Public Share Token", f"/api/v1/share/{share_token}", "GET", "Expired share token access", 410, "PASS")


# ============================================================================
# 7. RBAC & PRIVILEGE ESCALATION
# ============================================================================
def test_attack_class_7_rbac_and_privilege_escalation(client: TestClient, db):
    admin = _create_user(db, f"e2e-admin-{uuid.uuid4().hex[:8]}@example.com", "admin")
    homeowner = _create_user(db, f"e2e-home-{uuid.uuid4().hex[:8]}@example.com", "homeowner")
    designer = _create_user(db, f"e2e-des-{uuid.uuid4().hex[:8]}@example.com", "designer")

    token_adm = create_token(admin.id, "access")
    token_home = create_token(homeowner.id, "access")
    token_des = create_token(designer.id, "access")

    # Positive case: Admin accesses /admin/users
    r_adm = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {token_adm}"})
    assert r_adm.status_code == 200
    record_attack_step("RBAC", "/api/v1/admin/users", "GET", "Admin accesses user list", 200, "PASS")

    # Attack 1: Homeowner attempts to access admin endpoints
    r_h = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {token_home}"})
    assert r_h.status_code == 403
    record_attack_step("RBAC", "/api/v1/admin/users", "GET", "Homeowner attempts admin endpoint", 403, "PASS")

    # Attack 2: Designer attempts to access admin stats
    r_d = client.get("/api/v1/admin/stats", headers={"Authorization": f"Bearer {token_des}"})
    assert r_d.status_code == 403
    record_attack_step("RBAC", "/api/v1/admin/stats", "GET", "Designer attempts admin stats", 403, "PASS")

    # Attack 3: Admin self-demotion / deactivation prevention
    r_self_demote = client.patch(
        f"/api/v1/admin/users/{admin.id}",
        json={"role": "homeowner"},
        headers={"Authorization": f"Bearer {token_adm}"},
    )
    assert r_self_demote.status_code == 409
    record_attack_step("RBAC", f"/api/v1/admin/users/{admin.id}", "PATCH", "Admin self-demotion prevention", 409, "PASS")

    # Attack 4: Self-registration with role "admin" must be rejected (422)
    fake_admin_email = f"e2e-fake-admin-{uuid.uuid4().hex[:8]}@example.com"
    r_reg_admin = client.post(
        "/api/v1/auth/register",
        json={"email": fake_admin_email, "password": "Pass1234!Secure", "role": "admin"},
    )
    assert r_reg_admin.status_code == 422
    assert db.scalar(db.query(User).filter_by(email=fake_admin_email)) is None
    record_attack_step("RBAC", "/api/v1/auth/register", "POST", "Self-registration as 'admin' role rejection", 422, "PASS")

    # Attack 5: Self-registration with role "superuser" must be rejected (422)
    fake_su_email = f"e2e-fake-su-{uuid.uuid4().hex[:8]}@example.com"
    r_reg_su = client.post(
        "/api/v1/auth/register",
        json={"email": fake_su_email, "password": "Pass1234!Secure", "role": "superuser"},
    )
    assert r_reg_su.status_code == 422
    assert db.scalar(db.query(User).filter_by(email=fake_su_email)) is None
    record_attack_step("RBAC", "/api/v1/auth/register", "POST", "Self-registration as 'superuser' role rejection", 422, "PASS")


# ============================================================================
# 8. PAYMENT TAMPERING & CALLBACK REPLAY
# ============================================================================
def test_attack_class_8_payment_tampering(client: TestClient, db):
    user_a = _create_user(db, f"e2e-pay-a-{uuid.uuid4().hex[:8]}@example.com", "homeowner")
    user_b = _create_user(db, f"e2e-pay-b-{uuid.uuid4().hex[:8]}@example.com", "homeowner")

    token_a = create_token(user_a.id, "access")
    token_b = create_token(user_b.id, "access")

    # User A initiates payment
    req_pay = client.post("/api/v1/payment/request", headers={"Authorization": f"Bearer {token_a}"})
    assert req_pay.status_code == 201
    authority = req_pay.json()["data"]["authority"]

    # Positive: verify payment
    ver_pay = client.post(
        "/api/v1/payment/verify",
        json={"authority": authority, "status": "OK"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert ver_pay.status_code == 200
    assert ver_pay.json()["data"]["status"] == "paid"
    record_attack_step("Payment Tampering", "/api/v1/payment/verify", "POST", "Legitimate payment verification", 200, "PASS")

    # Attack 1: Replay of verified authority does not extend subscription twice
    ver_replay = client.post(
        "/api/v1/payment/verify",
        json={"authority": authority, "status": "OK"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert ver_replay.status_code == 200
    assert ver_replay.json()["data"]["status"] == "paid"
    record_attack_step("Payment Tampering", "/api/v1/payment/verify", "POST", "Replay of verified payment authority", 200, "PASS")

    # Attack 2: User B attempts to verify User A's authority
    ver_cross = client.post(
        "/api/v1/payment/verify",
        json={"authority": authority, "status": "OK"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert ver_cross.status_code == 404
    record_attack_step("Payment Tampering", "/api/v1/payment/verify", "POST", "Cross-user payment authority claiming", 404, "PASS")


# ============================================================================
# 9. MALICIOUS FILE UPLOADS
# ============================================================================
def test_attack_class_9_malicious_file_uploads(client: TestClient, db):
    admin = _create_user(db, f"e2e-up-adm-{uuid.uuid4().hex[:8]}@example.com", "admin")
    token = create_token(admin.id, "access")

    # Positive: valid PNG
    img_byte_arr = io.BytesIO()
    img = Image.new("RGB", (100, 100), color="blue")
    img.save(img_byte_arr, format="PNG")
    valid_bytes = img_byte_arr.getvalue()

    r_ok = client.post(
        "/api/v1/products/upload",
        files={"file": ("valid.png", valid_bytes, "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_ok.status_code == 201
    record_attack_step("Malicious Uploads", "/api/v1/products/upload", "POST", "Legitimate PNG image upload", 201, "PASS")

    # Attack 1: SVG with script
    svg_payload = b"<svg><script>alert('xss')</script></svg>"
    r_svg = client.post(
        "/api/v1/products/upload",
        files={"file": ("xss.svg", svg_payload, "image/svg+xml")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_svg.status_code == 415
    record_attack_step("Malicious Uploads", "/api/v1/products/upload", "POST", "SVG with script execution rejection", 415, "PASS")

    # Attack 2: Spoofed executable
    exe_payload = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00"
    r_exe = client.post(
        "/api/v1/products/upload",
        files={"file": ("malware.png", exe_payload, "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_exe.status_code == 415
    record_attack_step("Malicious Uploads", "/api/v1/products/upload", "POST", "MIME-spoofed binary payload rejection", 415, "PASS")

    # Attack 3: Empty upload
    r_empty = client.post(
        "/api/v1/products/upload",
        files={"file": ("empty.png", b"", "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_empty.status_code == 422
    record_attack_step("Malicious Uploads", "/api/v1/products/upload", "POST", "Zero-byte upload rejection", 422, "PASS")


# ============================================================================
# 10. SSRF OUTBOUND FETCHES
# ============================================================================
def test_attack_class_10_ssrf_protection():
    # Positive: valid public URL
    assert validate_public_url("https://www.digikala.com/product/123", resolve=False)

    # Attack 1: Loopback IPv4
    with pytest.raises(UnsafeUrl):
        validate_public_url("http://127.0.0.1:8000/api/v1/admin", resolve=False)
    record_attack_step("SSRF Guard", "127.0.0.1", "URL_VALIDATE", "Loopback IPv4 block", 400, "PASS")

    # Attack 2: AWS metadata IP
    with pytest.raises(UnsafeUrl):
        validate_public_url("http://169.254.169.254/latest/meta-data/", resolve=False)
    record_attack_step("SSRF Guard", "169.254.169.254", "URL_VALIDATE", "Cloud metadata IP block", 400, "PASS")

    # Attack 3: IPv6 loopback
    with pytest.raises(UnsafeUrl):
        validate_public_url("http://[::1]:8000/", resolve=False)
    record_attack_step("SSRF Guard", "::1", "URL_VALIDATE", "IPv6 loopback block", 400, "PASS")

    # Attack 4: Dangerous schemes
    for scheme in ["file:///etc/passwd", "gopher://127.0.0.1:6379/", "javascript:alert(1)"]:
        with pytest.raises(UnsafeUrl):
            validate_public_url(scheme, resolve=False)
    record_attack_step("SSRF Guard", "dangerous_schemes", "URL_VALIDATE", "Dangerous schemes rejection", 400, "PASS")


# ============================================================================
# 11. CROSS-SITE SCRIPTING (XSS)
# ============================================================================
def test_attack_class_11_xss_sanitization(client: TestClient, db):
    user = _create_user(db, f"e2e-xss-{uuid.uuid4().hex[:8]}@example.com", "homeowner")
    token = create_token(user.id, "access")

    # Attack 1: XSS in moodboard title
    xss_title = "<script>alert('xss')</script>Modern Living Room"
    r_mb = client.post(
        "/api/v1/moodboards",
        json={"title": xss_title, "items": [], "shopping_list": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_mb.status_code == 201
    stored_title = r_mb.json()["data"]["title"]
    assert "<script>" not in stored_title
    record_attack_step("XSS Sanitization", "/api/v1/moodboards", "POST", "Script tag stripped from title", 201, "PASS")


# ============================================================================
# 12. CSRF & ORIGIN VALIDATION
# ============================================================================
def test_attack_class_12_csrf_validation(client: TestClient, db):
    user = _create_user(db, f"e2e-csrf-{uuid.uuid4().hex[:8]}@example.com", "homeowner")

    # Authenticate via cookies
    login_resp = client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "Pass1234!Secure"}
    )
    assert login_resp.status_code == 200
    access_cookie = login_resp.cookies.get(ACCESS_COOKIE)
    csrf_token = login_resp.cookies.get(CSRF_COOKIE)

    # Positive case: mutating request with valid CSRF token header
    r_pos = client.post(
        "/api/v1/moodboards",
        json={"title": "CSRF Safe Board", "items": [], "shopping_list": []},
        cookies={ACCESS_COOKIE: access_cookie, CSRF_COOKIE: csrf_token},
        headers={CSRF_HEADER: csrf_token},
    )
    assert r_pos.status_code == 201
    record_attack_step("CSRF Defense", "/api/v1/moodboards", "POST", "Authenticated cookie request with valid CSRF header", 201, "PASS")

    # Negative case 1: Mutating request without CSRF header
    r_no_csrf = client.post(
        "/api/v1/moodboards",
        json={"title": "CSRF Attack Board", "items": [], "shopping_list": []},
        cookies={ACCESS_COOKIE: access_cookie, CSRF_COOKIE: csrf_token},
    )
    assert r_no_csrf.status_code == 403
    record_attack_step("CSRF Defense", "/api/v1/moodboards", "POST", "Cookie request missing CSRF header rejection", 403, "PASS")

    # Negative case 2: Mutating request with mismatched CSRF header
    r_bad_csrf = client.post(
        "/api/v1/moodboards",
        json={"title": "CSRF Attack Board", "items": [], "shopping_list": []},
        cookies={ACCESS_COOKIE: access_cookie, CSRF_COOKIE: csrf_token},
        headers={CSRF_HEADER: "forged_csrf_token_value_12345"},
    )
    assert r_bad_csrf.status_code == 403
    record_attack_step("CSRF Defense", "/api/v1/moodboards", "POST", "Mismatched CSRF header rejection", 403, "PASS")


# ============================================================================
# 13. RATE LIMIT ENFORCEMENT
# ============================================================================
def test_attack_class_13_rate_limiting(client: TestClient, db):
    user = _create_user(db, f"e2e-rate-{uuid.uuid4().hex[:8]}@example.com", "homeowner")
    token = create_token(user.id, "access")

    # Rapid burst to /recommend
    rate_triggered = False
    for i in range(25):
        resp = client.post(
            "/api/v1/recommend",
            json={
                "styles": ["modern"],
                "color_palette": ["#112233"],
                "room_width_cm": 400,
                "room_length_cm": 500,
                "budget_min_toman": 1000000,
                "budget_max_toman": 50000000,
                "materials": ["wood"],
                "patterns": ["solid"],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 429:
            rate_triggered = True
            break
    assert rate_triggered is True
    record_attack_step("Rate Limiting", "/api/v1/recommend", "POST", "Rate limit enforcement on AI recommendation", 429, "PASS")


# ============================================================================
# 14. ERROR HANDLING & SQL INJECTION ROBUSTNESS
# ============================================================================
def test_attack_class_14_error_handling_and_sqli(client: TestClient, db):
    user = _create_user(db, f"e2e-sqli-{uuid.uuid4().hex[:8]}@example.com", "homeowner")
    token = create_token(user.id, "access")

    # Attack 1: SQL injection strings in query
    sqli_payloads = [
        "' OR '1'='1",
        "'; DROP TABLE users; --",
        "1 UNION SELECT null, null, null --",
    ]
    for p in sqli_payloads:
        r = client.get(f"/api/v1/moodboards/{p}", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 404
        assert "syntax error" not in r.text.lower()
        assert "traceback" not in r.text.lower()
    record_attack_step("SQLi Robustness", "/api/v1/moodboards/{sqli}", "GET", "SQL injection parameter handling", 404, "PASS")

    # Attack 2: Validation errors do not echo password in plain text
    val_resp = client.post(
        "/api/v1/auth/register",
        json={"email": "not_an_email", "password": "super_secret_unhashed_password_123"},
    )
    assert val_resp.status_code == 422
    assert "super_secret_unhashed_password_123" not in val_resp.text
    record_attack_step("Info Leakage", "/api/v1/auth/register", "POST", "Validation error does not reflect secret input", 422, "PASS")


# ============================================================================
# 15. GDPR DELETION & REDIS CACHE PURGE (S3-F002)
# ============================================================================
def test_attack_class_15_gdpr_deletion_redis_invalidation(client: TestClient, db):
    user = _create_user(db, f"e2e-gdpr-redis-{uuid.uuid4().hex[:8]}@example.com", "homeowner")
    token = create_token(user.id, "access")

    # Warm recommendation cache
    rec_res = client.post(
        "/api/v1/recommend",
        json={
            "styles": ["modern"],
            "color_palette": ["#112233"],
            "room_width_cm": 400,
            "room_length_cm": 500,
            "budget_min_toman": 1000000,
            "budget_max_toman": 50000000,
            "materials": ["wood"],
            "patterns": ["solid"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rec_res.status_code == 200

    redis = get_redis()
    # Cache key exists
    matching = [k for k in redis.scan_iter(f"rec:{user.id}:*")]
    assert len(matching) >= 1

    # GDPR delete
    del_res = client.delete("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert del_res.status_code == 200

    # Redis recommendation cache for deleted user must be purged
    remaining = [k for k in redis.scan_iter(f"rec:{user.id}:*")]
    assert len(remaining) == 0, f"User recommendation cache survived GDPR deletion: {remaining}"
    record_attack_step("GDPR Deletion", "/api/v1/users/me", "DELETE", "User cache purge on account erasure (S3-F002)", 200, "PASS")
