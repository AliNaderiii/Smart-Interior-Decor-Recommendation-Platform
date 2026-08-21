"""Stage 03 · GDPR / privacy (probe G-01…G-03, P-01, L-01, T-41 … T-46).

Erasure (Art. 17), export (Art. 15/20), audit-trail pseudonymisation, and the
promise that logs never carry tokens, passwords or raw addresses.
"""
from __future__ import annotations

import logging

import pytest
from sqlalchemy import func, select

from app.api.routes.users import _truncate_ip, pseudonym_for
from app.core.log_redaction import RedactingFilter, pseudonymise_email, redact
from app.models.audit_log import AuditLog
from app.models.feedback import ProductFeedback
from app.models.moodboard import Moodboard
from app.models.quiz import StyleQuiz
from app.models.user import User

QUIZ_BODY = {
    "styles": ["modern"], "color_palette": [], "room_width_cm": 300,
    "room_length_cm": 300, "budget_min_toman": 0, "budget_max_toman": 100,
    "materials": [], "patterns": [],
}


def _populate(client, headers):
    client.post("/api/v1/quiz", headers=headers, json=QUIZ_BODY)
    client.post("/api/v1/moodboards", headers=headers,
                json={"title": "board", "items": [], "shopping_list": []})


# ------------------------------------------------------------------- erasure

def test_erasure_removes_every_owned_row(client, db, make_user):
    actor = make_user()
    uid = actor["user"]["id"]
    _populate(client, actor["headers"])

    resp = client.delete("/api/v1/users/me", headers=actor["headers"])
    assert resp.status_code == 200, resp.text

    db.expire_all()
    assert db.get(User, uid) is None
    for model, column in (
        (StyleQuiz, StyleQuiz.user_id), (Moodboard, Moodboard.user_id),
        (ProductFeedback, ProductFeedback.user_id),
    ):
        remaining = db.scalar(
            select(func.count()).select_from(model).where(column == uid))
        assert remaining == 0, f"{model.__name__} rows survived erasure"


def test_erasure_pseudonymises_the_audit_trail(client, db, make_user):
    """G-02: the trail survives, the link to the person does not."""
    actor = make_user()
    uid = actor["user"]["id"]
    _populate(client, actor["headers"])

    before = db.scalar(select(func.count()).select_from(AuditLog)
                       .where(AuditLog.user_id == uid))
    assert before > 0, "the fixture should have produced audit rows"

    resp = client.delete("/api/v1/users/me", headers=actor["headers"])
    assert resp.status_code == 200, resp.text
    pseudonym = resp.json()["data"]["audit_pseudonym"]

    db.expire_all()
    assert db.scalar(select(func.count()).select_from(AuditLog)
                     .where(AuditLog.user_id == uid)) == 0
    rows = db.scalars(select(AuditLog).where(AuditLog.user_id == pseudonym)).all()
    assert len(rows) >= before, "the security trail was destroyed, not pseudonymised"
    for row in rows:
        assert row.user_agent == "", "user agent is personal data"
        assert row.ip in ("", "0.0.0.0") or row.ip.endswith(".0"), row.ip


def test_the_erasure_itself_is_audited_under_the_pseudonym(client, db, make_user):
    """G-03: and the record must not re-introduce the identity it just erased."""
    from app.models.audit_log import ACTION_USER_DELETE

    actor = make_user()
    uid = actor["user"]["id"]
    resp = client.delete("/api/v1/users/me", headers=actor["headers"])
    pseudonym = resp.json()["data"]["audit_pseudonym"]

    db.expire_all()
    row = db.scalars(select(AuditLog).where(
        AuditLog.action == ACTION_USER_DELETE,
        AuditLog.user_id == pseudonym)).first()
    assert row is not None, "erasure left no audit record"
    assert row.user_id != uid
    assert row.user_agent == ""


def test_the_erased_session_stops_working(client, make_user):
    actor = make_user()
    assert client.delete("/api/v1/users/me",
                         headers=actor["headers"]).status_code == 200
    assert client.get("/api/v1/auth/me",
                      headers=actor["headers"]).status_code == 401


def test_erasure_requires_authentication(client):
    assert client.delete("/api/v1/users/me").status_code == 401


def test_pseudonym_is_stable_keyed_and_column_sized():
    a, b = pseudonym_for("abc123"), pseudonym_for("abc123")
    assert a == b, "the pseudonym must be stable so a trail stays joinable"
    assert a != pseudonym_for("abc124")
    assert len(a) == 32, "audit_logs.user_id is String(32)"
    assert "abc123" not in a


@pytest.mark.parametrize(("raw", "expected"), [
    ("203.0.113.42", "203.0.113.0"),
    ("10.1.2.3", "10.1.2.0"),
    ("", ""),
    ("not-an-ip", ""),
])
def test_ip_truncation(raw, expected):
    assert _truncate_ip(raw) == expected


def test_ipv6_is_truncated_to_a_prefix():
    out = _truncate_ip("2001:db8:1234:5678::1")
    assert out and out != "2001:db8:1234:5678::1"
    assert out.startswith("2001:db8:")


# -------------------------------------------------------------------- export

def test_export_returns_the_full_inventory(client, make_user):
    actor = make_user()
    _populate(client, actor["headers"])
    resp = client.get("/api/v1/users/me/export", headers=actor["headers"])
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    for section in ("account", "quizzes", "moodboards", "projects",
                    "product_feedback", "payments", "security_events",
                    "retention_notice"):
        assert section in data, f"export is missing {section}"
    assert data["account"]["email"] == actor["email"]
    assert len(data["quizzes"]) == 1
    assert len(data["moodboards"]) == 1


def test_export_never_contains_credentials(client, make_user):
    actor = make_user()
    resp = client.get("/api/v1/users/me/export", headers=actor["headers"])
    assert resp.status_code == 200
    body = resp.text
    assert "hashed_password" not in body
    assert actor["password"] not in body
    assert "$2b$" not in body, "a bcrypt hash leaked into the export"


def test_export_only_covers_the_caller(client, make_user):
    victim, actor = make_user(), make_user()
    _populate(client, victim["headers"])
    resp = client.get("/api/v1/users/me/export", headers=actor["headers"])
    assert resp.status_code == 200
    assert victim["email"] not in resp.text
    assert resp.json()["data"]["quizzes"] == []


def test_export_requires_authentication(client):
    assert client.get("/api/v1/users/me/export").status_code == 401


def test_export_is_rate_limited(client, make_user, reset_settings):
    """The most valuable single object a stolen session can request."""
    reset_settings(EXPORT_RATE_LIMIT_PER_HOUR=2)
    actor = make_user()
    codes = [client.get("/api/v1/users/me/export",
                        headers=actor["headers"]).status_code for _ in range(4)]
    assert 429 in codes, codes


# ----------------------------------------------------------- log redaction

@pytest.mark.parametrize("secret", [
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJlLXZhbHVl",
    "Bearer abcdef0123456789abcdef",
    "authorization: Bearer sk-live-0123456789",
    "?token=super-secret-value&x=1",
    "password=hunter2seven",
])
def test_secrets_are_redacted_from_log_text(secret):
    out = redact(secret)
    assert "[REDACTED]" in out
    for fragment in ("eyJzdWIiOiIxIn0", "sk-live-0123456789", "hunter2seven",
                     "super-secret-value"):
        assert fragment not in out


def test_emails_are_pseudonymised_in_logs():
    out = redact("login failed for alice.smith@example.com")
    assert "alice.smith@example.com" not in out
    assert "example.com" in out, "the domain is useful and not identifying"


def test_pseudonymise_email_is_stable_and_non_reversible():
    a = pseudonymise_email("alice@example.com")
    assert a == pseudonymise_email("alice@example.com")
    assert a != pseudonymise_email("bob@example.com")
    assert "alice" not in a


def test_card_numbers_are_redacted():
    out = redact("card 4111 1111 1111 1111 declined")
    assert "4111" not in out


def test_ordinary_numbers_survive_redaction():
    """A price must not be mistaken for a card number."""
    assert "1500000" in redact("budget 1500000 toman")


def test_redacting_filter_scrubs_a_real_log_record(caplog):
    logger = logging.getLogger("test.redaction")
    logger.addFilter(RedactingFilter())
    with caplog.at_level(logging.INFO, logger="test.redaction"):
        logger.info("token=%s for %s",
                    "eyJhbGciOiJIUzI1NiJ9.eyJhIjoxfQ.c2ln", "bob@example.com")
    text = caplog.text
    assert "eyJhIjoxfQ" not in text
    assert "bob@example.com" not in text


def test_login_failures_do_not_log_the_password(client, caplog, demo_user):
    with caplog.at_level(logging.DEBUG):
        client.post("/api/v1/auth/login",
                    json={"email": demo_user["email"], "password": "SuperSecret123!"})
    assert "SuperSecret123!" not in caplog.text


def test_audit_rows_never_store_a_password_or_token(client, db, demo_user):
    client.post("/api/v1/auth/login",
                json={"email": demo_user["email"], "password": "Demo1234!"})
    rows = db.scalars(select(AuditLog).order_by(
        AuditLog.created_at.desc()).limit(20)).all()
    for row in rows:
        blob = f"{row.detail} {row.user_agent}"
        assert "Demo1234!" not in blob
        assert "eyJ" not in blob, "a JWT reached the audit trail"


def test_failed_logins_record_a_pseudonym_not_the_address(client, db):
    client.post("/api/v1/auth/login",
                json={"email": "victim@example.com", "password": "Wrong123!x"})
    rows = db.scalars(select(AuditLog).order_by(
        AuditLog.created_at.desc()).limit(5)).all()
    joined = " ".join(r.detail or "" for r in rows)
    assert "victim@example.com" not in joined
    assert "account=" in joined
