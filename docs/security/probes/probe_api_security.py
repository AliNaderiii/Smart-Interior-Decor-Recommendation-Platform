#!/usr/bin/env python3
"""Stage 03 penetration-probe harness — runs the same checks before and after.

This script is deliberately **assertion-free**: every check prints what the
application actually did next to what a hardened application should do, and the
summary counts the checks whose observed behaviour is insecure. Running it on
the pre-hardening tree and on the post-hardening tree produces two directly
comparable evidence files.

Usage
-----
    cd backend
    .venv/bin/python ../docs/security/probes/probe_api_security.py [--label BEFORE]

Environment
-----------
``PROBE_REDIS_URL``  optional; a real Redis URL. Defaults to fakeredis.
``PROBE_DB_URL``     optional; defaults to a throwaway SQLite file.
"""
from __future__ import annotations

import argparse
import io
import logging
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

WORKDIR = Path(tempfile.mkdtemp(prefix="apiprobe-"))
os.environ.setdefault("DATABASE_URL", os.environ.get("PROBE_DB_URL", f"sqlite:///{WORKDIR / 'probe.sqlite3'}"))
os.environ.setdefault("REDIS_URL", os.environ.get("PROBE_REDIS_URL", ""))
os.environ["APP_ENV"] = os.environ.get("PROBE_APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "probe-secret-key-that-is-long-enough-000000")
os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault("EMBEDDING_BACKEND", "hash")
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("PAYMENT_PROVIDER", "mock")
os.environ.setdefault("LOCAL_STORAGE_DIR", str(WORKDIR / "storage"))
os.environ.setdefault("COOKIE_SECURE", "false")

BACKEND = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models import Base  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.models.subscription import Subscription  # noqa: E402
from app.models.user import User  # noqa: E402

RESULTS: list[dict] = []


def check(check_id: str, title: str, expected: str, observed: str, secure: bool) -> None:
    RESULTS.append({
        "id": check_id, "title": title, "expected": expected,
        "observed": observed, "secure": secure,
    })
    flag = "SECURE  " if secure else "INSECURE"
    print(f"[{flag}] {check_id} {title}")
    print(f"           expected: {expected}")
    print(f"           observed: {observed}")


def bootstrap() -> tuple[TestClient, dict]:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    products = []
    for i in range(6):
        p = Product(
            title=f"Probe product {i}", category="sofa", price_toman=1_000_000 + i,
            image_url="https://example.com/p.jpg", seller_link="https://digikala.com/p",
            colors=["#111111"], styles=["modern"], materials=["wood"], patterns=["solid"],
            width_cm=100, depth_cm=80, height_cm=70, description="probe seed product",
            extraction_confidence=1.0, is_verified=True,
            style_embedding=[0.01] * 512,
        )
        db.add(p)
        products.append(p)
    admin = User(email=f"probe-admin-{uuid.uuid4().hex[:6]}@probe.example.com",
                 hashed_password=hash_password("ProbeAdmin123!"), role="admin",
                 full_name="Probe Admin")
    admin.subscription = Subscription(plan="free", is_active=False)
    db.add(admin)
    db.commit()
    ctx = {"admin_email": admin.email, "admin_password": "ProbeAdmin123!",
           "product_id": products[0].id}
    db.close()

    from app.main import app

    # A route that raises, so the 500 path can be observed at all.
    @app.get("/api/v1/__probe/boom")
    def _boom():  # pragma: no cover - probe only
        raise RuntimeError("probe-triggered unhandled error")

    client = TestClient(app, raise_server_exceptions=False)
    return client, ctx


def _clear_register_throttle() -> None:
    """The probe legitimately creates many accounts; drop the per-IP counter.

    This does not weaken the check — R-03 below measures the register limit
    explicitly on a clean counter.
    """
    from app.core.redis_client import get_redis

    try:
        r = get_redis()
        for key in r.scan_iter("rl:register:*"):
            r.delete(key)
    except Exception:
        pass


def register(client: TestClient, role: str = "homeowner") -> dict:
    _clear_register_throttle()
    email = f"probe-{uuid.uuid4().hex[:8]}@probe.example.com"
    resp = client.post("/api/v1/auth/register", json={
        "email": email, "password": "ProbeUser123!", "full_name": "Probe", "role": role,
    })
    resp.raise_for_status()
    data = resp.json()["data"]
    return {"email": email, "password": "ProbeUser123!",
            "headers": {"Authorization": f"Bearer {data['access_token']}"},
            "user": data["user"]}


REQUIRED_HEADERS = {
    "content-security-policy", "x-frame-options", "x-content-type-options",
    "referrer-policy", "permissions-policy",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="RUN")
    args = ap.parse_args()

    print("=" * 78)
    print(f"STAGE 03 API SECURITY PROBE — {args.label}")
    print(f"redis: {os.environ['REDIS_URL'] or 'fakeredis (in-process)'}")
    print(f"db   : {os.environ['DATABASE_URL']}")
    print("=" * 78)

    client, ctx = bootstrap()
    admin_login = client.post("/api/v1/auth/login", json={
        "email": ctx["admin_email"], "password": ctx["admin_password"]})
    admin_h = {"Authorization": f"Bearer {admin_login.json()['data']['access_token']}"}

    # ---------------------------------------------------------------- headers
    r500 = client.get("/api/v1/__probe/boom")
    missing = REQUIRED_HEADERS - {k.lower() for k in r500.headers}
    body_leaks_trace = "Traceback" in r500.text or "RuntimeError" in r500.text
    check("H-01", "Security headers on an unhandled 500",
          "all 5 core headers present on the 500 response",
          f"status={r500.status_code} missing={sorted(missing) or 'none'}",
          not missing)
    check("H-02", "500 response body must not leak a stack trace / exception type",
          "generic JSON envelope, no traceback, no exception class name",
          f"body[:160]={r500.text[:160]!r}",
          not body_leaks_trace)

    r422 = client.post("/api/v1/auth/register", json={
        "email": "not-an-email", "password": "short", "secret_note": "s3cr3t-value-123"})
    echoes_input = "s3cr3t-value-123" in r422.text or "'input'" in r422.text
    check("H-03", "422 validation envelope must not reflect submitted values",
          "field name + message only",
          f"status={r422.status_code} reflects_input={echoes_input} body[:200]={r422.text[:200]!r}",
          not echoes_input)

    # ------------------------------------------------------------------ CORS
    pre = client.options("/api/v1/auth/login", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    check("C-01", "CORS must reject an unknown origin",
          "no access-control-allow-origin for https://evil.example",
          f"acao={pre.headers.get('access-control-allow-origin')!r}",
          pre.headers.get("access-control-allow-origin") is None)

    from app.core.config import Settings
    prod_cfg = Settings(APP_ENV="production", SECRET_KEY="x" * 48,
                        REDIS_URL="redis://r:6379/0",
                        FRONTEND_ORIGIN="https://app.example.com")
    try:
        from app.main import build_cors_origins  # type: ignore
        origins = build_cors_origins(prod_cfg)
    except Exception:
        origins = [prod_cfg.FRONTEND_ORIGIN, "http://localhost:5173", "http://localhost:4173"]
    localhost_in_prod = any("localhost" in o for o in origins)
    check("C-02", "Production CORS allowlist must not contain localhost origins",
          "['https://app.example.com']",
          f"{origins}",
          not localhost_in_prod)

    # -------------------------------------------------------- URL / stored XSS
    xss_link = "javascript:alert(document.cookie)"
    rp = client.post("/api/v1/products", headers=admin_h, json={
        "title": "Probe XSS", "category": "sofa", "price_toman": 100,
        "image_url": "https://example.com/i.jpg", "seller_link": xss_link,
        "styles": ["modern"]})
    stored = rp.status_code < 300 and rp.json()["data"]["seller_link"] == xss_link
    check("X-01", "javascript: URL in seller_link must be rejected",
          "422",
          f"status={rp.status_code} stored_verbatim={stored}",
          not stored)

    rp2 = client.post("/api/v1/products", headers=admin_h, json={
        "title": "<script>alert(1)</script>Sofa", "category": "sofa", "price_toman": 100,
        "image_url": "https://example.com/i.jpg", "styles": ["modern"],
        "description": "<img src=x onerror=alert(1)>nice"})
    if rp2.status_code < 300:
        d = rp2.json()["data"]
        dirty = "<script>" in d["title"] or "onerror" in d["description"]
    else:
        dirty = False
    check("X-02", "Admin-supplied product free text must be HTML-stripped",
          "no markup persisted",
          f"status={rp2.status_code} markup_persisted={dirty} title={rp2.json()['data']['title'][:60]!r}"
          if rp2.status_code < 300 else f"status={rp2.status_code}",
          not dirty)

    rp3 = client.post("/api/v1/products", headers=admin_h, json={
        "title": "Extra field probe", "category": "sofa", "price_toman": 100,
        "image_url": "https://example.com/i.jpg", "styles": ["modern"],
        "is_verified": True, "id": "attacker-chosen-id"})
    check("V-01", "Unknown fields on ProductIn must be rejected (mass assignment)",
          "422 extra_forbidden",
          f"status={rp3.status_code}",
          rp3.status_code == 422)

    rp4 = client.post("/api/v1/products", headers=admin_h, json={
        "title": "A" * 5000, "category": "sofa", "price_toman": 100,
        "image_url": "https://example.com/i.jpg", "styles": ["modern"]})
    check("V-02", "Oversized product title must be a 422, never a 500",
          "422",
          f"status={rp4.status_code}",
          rp4.status_code == 422)

    rp5 = client.post("/api/v1/products", headers=admin_h, json={
        "title": "Category probe", "category": "not-a-real-category", "price_toman": 100,
        "image_url": "https://example.com/i.jpg", "styles": ["modern"]})
    check("V-03", "Product category must be validated against the taxonomy",
          "422",
          f"status={rp5.status_code}",
          rp5.status_code == 422)

    # ---------------------------------------------------------------- uploads
    html_payload = b"<html><script>alert(document.domain)</script></html>"
    up = client.post("/api/v1/products/upload", headers=admin_h,
                     files={"file": ("evil.html", io.BytesIO(html_payload), "text/html")})
    served_ct = ""
    if up.status_code < 300:
        url = up.json()["data"]["product"]["image_url"]
        got = client.get(url)
        served_ct = got.headers.get("content-type", "")
    check("U-01", "Non-image upload (text/html) must be rejected",
          "415 or 422",
          f"status={up.status_code} served_content_type={served_ct!r}",
          up.status_code in (400, 415, 422))

    svg = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"></svg>'
    up2 = client.post("/api/v1/products/upload", headers=admin_h,
                      files={"file": ("logo.svg", io.BytesIO(svg), "image/svg+xml")})
    check("U-02", "SVG upload (scriptable image) must be rejected",
          "415 or 422",
          f"status={up2.status_code}",
          up2.status_code in (400, 415, 422))

    fake_jpg = b"MZ\x90\x00" + b"\x00" * 512          # PE binary named .jpg
    up3 = client.post("/api/v1/products/upload", headers=admin_h,
                      files={"file": ("payload.jpg", io.BytesIO(fake_jpg), "image/jpeg")})
    check("U-03", "Content-type spoofing must be caught by magic-byte sniffing",
          "415 or 422",
          f"status={up3.status_code}",
          up3.status_code in (400, 415, 422))

    trav = client.post("/api/v1/products/upload", headers=admin_h,
                       files={"file": ("../../../../etc/cron.d/evil.jpg",
                                       io.BytesIO(fake_jpg), "image/jpeg")})
    check("U-04", "Path-traversal filename must not escape the storage root",
          "rejected, or stored under a generated name inside the storage dir",
          f"status={trav.status_code} escaped={(WORKDIR / 'storage').exists() and any(p.name == 'evil.jpg' for p in Path('/tmp').glob('**/evil.jpg'))}",
          trav.status_code in (400, 415, 422))

    png = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    codes = []
    for _ in range(12):
        r = client.post("/api/v1/products/upload", headers=admin_h,
                        files={"file": ("x.png", io.BytesIO(png), "image/png")})
        codes.append(r.status_code)
    check("U-05", "Upload endpoint must be rate limited",
          "at least one 429 within 12 rapid uploads",
          f"status_codes={codes}",
          429 in codes)

    # ------------------------------------------------------- AI output sanitising
    import app.api.routes.products as products_mod

    class _EvilExtractor:
        def extract(self, _url):
            return {"colors": ["#112233"], "style": ["modern"], "material": ["wood"],
                    "patterns": ["solid"], "confidence": 0.9,
                    "description_for_embedding":
                        "<img src=x onerror=alert('ai')>a modern sofa"}

    orig = products_mod.FeatureExtractor
    products_mod.FeatureExtractor = lambda: _EvilExtractor()  # type: ignore
    try:
        ai = client.post("/api/v1/products/upload", headers=admin_h,
                         files={"file": ("ok.png", io.BytesIO(png), "image/png")})
        if ai.status_code < 300:
            p = ai.json()["data"]["product"]
            ai_dirty = "onerror" in p["title"] or "onerror" in p["description"]
            detail = f"title={p['title'][:60]!r}"
        else:
            ai_dirty = False
            detail = f"status={ai.status_code} (upload rejected before extraction)"
    finally:
        products_mod.FeatureExtractor = orig
    check("X-03", "AI-generated text must be HTML-stripped before persistence",
          "no markup in the stored title/description",
          f"markup_persisted={ai_dirty} {detail}",
          not ai_dirty)

    # ------------------------------------------------------------------ share
    designer = register(client, role="designer")
    proj = client.post("/api/v1/projects", headers=designer["headers"],
                       json={"name": "Probe project"})
    quiz = client.post("/api/v1/quiz", headers=designer["headers"], json={
        "styles": ["modern"], "color_palette": ["#fff"], "room_width_cm": 400,
        "room_length_cm": 500, "budget_min_toman": 1, "budget_max_toman": 100_000_000,
        "materials": ["wood"], "patterns": []})
    share = client.post(f"/api/v1/projects/{proj.json()['data']['id']}/share",
                        headers=designer["headers"],
                        json={"quiz_id": quiz.json()["data"]["id"]})
    token = share.json()["data"]["token"] if share.status_code < 300 else "missing"
    share_codes = [client.get(f"/api/v1/share/{token}").status_code for _ in range(40)]
    check("R-01", "Public share endpoint must be rate limited",
          "at least one 429 within 40 rapid reads",
          f"distinct_status={sorted(set(share_codes))}",
          429 in share_codes)

    nf = client.get("/api/v1/share/" + "z" * 43)
    check("R-02", "Unknown share token must not leak whether it ever existed",
          "404 with a generic message",
          f"status={nf.status_code} body={nf.text[:80]!r}",
          nf.status_code == 404)

    _clear_register_throttle()
    reg_codes = []
    reg_retry_after = None
    for _ in range(6):
        rr = client.post("/api/v1/auth/register", json={
            "email": f"flood-{uuid.uuid4().hex[:8]}@probe.example.com",
            "password": "ProbeUser123!", "full_name": "Flood"})
        reg_codes.append(rr.status_code)
        if rr.status_code == 429:
            reg_retry_after = rr.headers.get("retry-after")
    check("R-03", "Registration flooding must be throttled with Retry-After",
          "429 + Retry-After header",
          f"status_codes={reg_codes} retry_after={reg_retry_after!r}",
          429 in reg_codes and bool(reg_retry_after))

    lock_email = f"lock-{uuid.uuid4().hex[:6]}@probe.example.com"
    lock_codes, lock_retry = [], None
    for _ in range(7):
        lr = client.post("/api/v1/auth/login",
                         json={"email": lock_email, "password": "wrong-password"})
        lock_codes.append(lr.status_code)
        if lr.status_code == 429:
            lock_retry = lr.headers.get("retry-after")
    check("R-04", "Wrong-password lockout must engage and carry Retry-After",
          "401 x4 then 429 + Retry-After",
          f"status_codes={lock_codes} retry_after={lock_retry!r}",
          lock_codes[:4] == [401] * 4 and 429 in lock_codes and bool(lock_retry))

    # ------------------------------------------------------- cookie auth / CSRF
    cj = TestClient(client.app, raise_server_exceptions=False)
    _clear_register_throttle()
    cmail = f"cookie-{uuid.uuid4().hex[:6]}@probe.example.com"
    cj.post("/api/v1/auth/register",
            json={"email": cmail, "password": "ProbeUser123!", "full_name": "C"})
    clogin = cj.post("/api/v1/auth/login",
                     json={"email": cmail, "password": "ProbeUser123!"})
    raw_cookies = clogin.headers.get_list("set-cookie")
    access_cookie = next((c for c in raw_cookies if c.startswith("access_token=")), "")
    csrf = clogin.json()["data"].get("csrf_token")
    no_csrf = cj.post("/api/v1/moodboards", json={"title": "csrf attempt"})
    with_csrf = cj.post("/api/v1/moodboards", json={"title": "legit"},
                        headers={"X-CSRF-Token": csrf})
    check("K-01", "Auth cookies must be HttpOnly + SameSite",
          "HttpOnly and SameSite on the access cookie",
          f"set-cookie={access_cookie[:120]!r}",
          "HttpOnly" in access_cookie and "amesite" in access_cookie.lower())
    check("K-02", "Cookie-authenticated state change requires the CSRF header",
          "403 without X-CSRF-Token, 201 with it",
          f"without={no_csrf.status_code} with={with_csrf.status_code}",
          no_csrf.status_code == 403 and with_csrf.status_code == 201)

    logout = cj.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    replay = cj.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf}, json={})
    check("K-03", "Refresh token must be revoked after logout (replay blocked)",
          "401 on refresh after logout",
          f"logout={logout.status_code} refresh_replay={replay.status_code}",
          replay.status_code == 401)

    # ------------------------------------------------------------ IDOR / RBAC
    alice = register(client)
    bob = register(client)
    board = client.post("/api/v1/moodboards", headers=alice["headers"],
                        json={"title": "Alice board"})
    bid = board.json()["data"]["id"]
    idor = client.get(f"/api/v1/moodboards/{bid}", headers=bob["headers"])
    check("A-01", "Cross-tenant moodboard read must 404",
          "404", f"status={idor.status_code}", idor.status_code == 404)
    idor_d = client.delete(f"/api/v1/moodboards/{bid}", headers=bob["headers"])
    check("A-02", "Cross-tenant moodboard delete must 404",
          "404", f"status={idor_d.status_code}", idor_d.status_code == 404)
    rbac = client.get("/api/v1/admin/users", headers=alice["headers"])
    check("A-03", "Homeowner must not reach admin endpoints",
          "403", f"status={rbac.status_code}", rbac.status_code == 403)
    rbac2 = client.get("/api/v1/projects", headers=alice["headers"])
    check("A-04", "Homeowner must not reach designer endpoints",
          "403", f"status={rbac2.status_code}", rbac2.status_code == 403)
    esc = client.patch(f"/api/v1/admin/users/{alice['user']['id']}",
                       headers=alice["headers"], json={"role": "admin"})
    check("A-05", "Self privilege escalation via admin route must fail",
          "403", f"status={esc.status_code}", esc.status_code == 403)

    admin_id = admin_login.json()["data"]["user"]["id"]
    self_demote = client.patch(f"/api/v1/admin/users/{admin_id}", headers=admin_h,
                               json={"role": "homeowner"})
    check("A-06", "Admin must not be able to demote itself (lockout / audit gap)",
          "409 or 422",
          f"status={self_demote.status_code}",
          self_demote.status_code in (400, 409, 422))
    if self_demote.status_code < 300:  # undo so later checks still work
        db = SessionLocal()
        u = db.get(User, admin_id)
        u.role = "admin"
        db.commit()
        db.close()

    unknown_admin_patch = client.patch(f"/api/v1/admin/users/{alice['user']['id']}",
                                       headers=admin_h,
                                       json={"is_active": True, "hashed_password": "x"})
    check("V-04", "Unknown fields on the admin user patch must be rejected",
          "422",
          f"status={unknown_admin_patch.status_code}",
          unknown_admin_patch.status_code == 422)

    # ------------------------------------------------------------ audit / GDPR
    from app.models.audit_log import AuditLog

    db = SessionLocal()
    before_actions = {a for (a,) in db.query(AuditLog.action).distinct()}
    db.close()
    client.patch(f"/api/v1/admin/users/{bob['user']['id']}", headers=admin_h,
                 json={"role": "designer"})
    db = SessionLocal()
    after_actions = {a for (a,) in db.query(AuditLog.action).distinct()}
    db.close()
    check("L-01", "Admin role change must be written to the audit log",
          "role_change present",
          f"new_actions={sorted(after_actions - before_actions) or 'none'}",
          "role_change" in after_actions)

    victim = register(client)
    client.post("/api/v1/feedback", headers=victim["headers"],
                json={"product_id": ctx["product_id"], "signal": 1})
    client.post("/api/v1/moodboards", headers=victim["headers"], json={"title": "gone"})
    vid = victim["user"]["id"]
    dele = client.delete("/api/v1/users/me", headers=victim["headers"])
    db = SessionLocal()
    from app.models.feedback import ProductFeedback
    leftover_fb = db.query(ProductFeedback).filter(ProductFeedback.user_id == vid).count()
    leftover_audit = db.query(AuditLog).filter(AuditLog.user_id == vid).count()
    audit_delete_rows = db.query(AuditLog).filter(
        AuditLog.action == "user_delete").count()
    db.close()
    check("G-01", "GDPR delete must remove per-user feedback rows",
          "0 rows left",
          f"status={dele.status_code} product_feedback_rows_left={leftover_fb}",
          leftover_fb == 0)
    check("G-02", "GDPR delete must pseudonymise/clear the user's audit rows",
          "0 rows still bound to the deleted user id",
          f"audit_rows_still_bound={leftover_audit}",
          leftover_audit == 0)
    check("G-03", "GDPR delete must itself be audited",
          ">=1 user_delete audit row",
          f"user_delete_rows={audit_delete_rows}",
          audit_delete_rows >= 1)

    # ------------------------------------------------------------ log hygiene
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setLevel(logging.DEBUG)
    root = logging.getLogger()
    root.addHandler(handler)
    prev_level = root.level
    root.setLevel(logging.DEBUG)
    try:
        target = f"log-probe-{uuid.uuid4().hex[:6]}@probe.example.com"
        for _ in range(6):
            client.post("/api/v1/auth/login",
                        json={"email": target, "password": "wrong-password"})
    finally:
        root.removeHandler(handler)
        root.setLevel(prev_level)
    logged = buf.getvalue()
    check("P-01", "Logs must not contain raw account identifiers (personal data)",
          "email addresses masked or hashed",
          f"raw_email_in_logs={target in logged}",
          target not in logged)

    # --------------------------------------------------- auth timing / lockout
    known = register(client)
    def _t(email: str) -> float:
        t0 = time.perf_counter()
        client.post("/api/v1/auth/login", json={"email": email, "password": "Wrong123!x"})
        return time.perf_counter() - t0
    t_known = min(_t(known["email"]) for _ in range(3))
    t_unknown = min(_t(f"nobody-{uuid.uuid4().hex[:6]}@probe.example.com") for _ in range(3))
    ratio = t_known / max(t_unknown, 1e-6)
    check("T-01", "Login timing must not disclose whether an account exists",
          "ratio between 0.5x and 2x",
          f"known={t_known*1000:.1f}ms unknown={t_unknown*1000:.1f}ms ratio={ratio:.1f}x",
          0.5 <= ratio <= 2.0)

    # ---------------------------------------------- Redis outage -> fail closed
    from app.core import brute_force, rate_limit  # noqa: F401
    from app.core import redis_client

    class _DeadRedis:
        def __getattr__(self, _name):
            def _boom(*_a, **_kw):
                raise ConnectionError("probe: redis is down")
            return _boom

    saved = redis_client._client
    redis_client._client = _DeadRedis()
    try:
        codes = [client.post("/api/v1/auth/login", json={
            "email": known["email"], "password": "still-wrong"}).status_code
            for _ in range(8)]
    finally:
        redis_client._client = saved
    prod_fail_closed = 503 in codes
    check("D-01", "Brute-force control behaviour when Redis is unavailable",
          "production: fail closed (503). dev/test: documented fail-open",
          f"APP_ENV={os.environ['APP_ENV']} status_codes={codes}",
          prod_fail_closed or os.environ["APP_ENV"] != "production")

    # --------------------------------------------------------------- summary
    insecure = [r for r in RESULTS if not r["secure"]]
    print()
    print("=" * 78)
    print(f"SUMMARY {args.label}: {len(RESULTS)} checks, "
          f"{len(RESULTS) - len(insecure)} secure, {len(insecure)} INSECURE")
    for r in insecure:
        print(f"  INSECURE  {r['id']}  {r['title']}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
