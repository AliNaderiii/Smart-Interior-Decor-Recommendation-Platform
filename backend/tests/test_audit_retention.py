"""Stage 07 — audit-log retention enforcement (IR-SEC-007 / T-43).

The GDPR export endpoint promises a 180-day retention window; this test locks
in the script that enforces it: old rows are purged, fresh rows survive,
``--dry-run`` changes nothing, and a disabled retention (0) is a no-op.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.session import SessionLocal
from app.models.audit_log import AuditLog


def _add_row(db, created_at: datetime, action: str = "test_action") -> AuditLog:
    row = AuditLog(action=action, detail=f"row-{action}", ip="127.0.0.1", user_agent="test")
    row.created_at = created_at
    db.add(row)
    return row


def test_prune_deletes_only_expired_rows(monkeypatch):
    import scripts.prune_audit_logs as prune

    monkeypatch.setattr("sys.argv", ["prune_audit_logs.py"])
    monkeypatch.setenv("AUDIT_LOG_RETENTION_DAYS", "7")
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        old = _add_row(db, now - timedelta(days=30))
        fresh = _add_row(db, now - timedelta(days=1))
        db.commit()
        old_id, fresh_id = old.id, fresh.id

    rc = prune.main()
    assert rc == 0

    with SessionLocal() as db:
        assert db.get(AuditLog, old_id) is None, "expired row must be purged"
        assert db.get(AuditLog, fresh_id) is not None, "fresh row must survive"


def test_prune_dry_run_changes_nothing(monkeypatch):
    import scripts.prune_audit_logs as prune

    monkeypatch.setattr("sys.argv", ["prune_audit_logs.py", "--dry-run"])
    monkeypatch.setenv("AUDIT_LOG_RETENTION_DAYS", "7")
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        old = _add_row(db, now - timedelta(days=30))
        db.commit()
        old_id = old.id

    rc = prune.main()
    assert rc == 0

    with SessionLocal() as db:
        assert db.get(AuditLog, old_id) is not None, "dry-run must not delete"


def test_prune_disabled_when_retention_zero(monkeypatch):
    import scripts.prune_audit_logs as prune

    monkeypatch.setattr("sys.argv", ["prune_audit_logs.py"])
    monkeypatch.setenv("AUDIT_LOG_RETENTION_DAYS", "0")
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        old = _add_row(db, now - timedelta(days=30))
        db.commit()
        old_id = old.id

    assert prune.main() == 0

    with SessionLocal() as db:
        assert db.get(AuditLog, old_id) is not None, "0 retention must disable pruning"
