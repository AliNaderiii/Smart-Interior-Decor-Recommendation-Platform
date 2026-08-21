"""Enforce the documented audit-log retention window (IR-SEC-007 / T-43).

The GDPR export endpoint promises data subjects that security events are kept
for 180 days; nothing deleted them. This script is that enforcement:

    AUDIT_LOG_RETENTION_DAYS=180 python scripts/prune_audit_logs.py
    AUDIT_LOG_RETENTION_DAYS=180 python scripts/prune_audit_logs.py --dry-run

Behaviour:

* Deletes ``audit_logs`` rows older than ``now() - retention`` (default 180
  days, env ``AUDIT_LOG_RETENTION_DAYS``; 0 disables pruning).
* Runs inside one transaction and reports the exact row count purged — the
  metric a scheduled job (see docker-compose.prod.yml ``maintenance``) should
  alert on: a run that deletes nothing while rows are due means the job broke.
* ``--dry-run`` prints what *would* be deleted without touching data.

Safe by construction: it never touches other tables, never truncates, and
deleting from the tail of the table cannot interfere with the rows the
GDPR erasure path pseudonymises (that path updates, it does not delete).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("prune-audit-logs")


def retention_days() -> int:
    raw = os.environ.get("AUDIT_LOG_RETENTION_DAYS", "180")
    try:
        days = int(raw)
    except ValueError:
        raise SystemExit(f"AUDIT_LOG_RETENTION_DAYS must be an integer, got {raw!r}")
    if days < 0:
        raise SystemExit("AUDIT_LOG_RETENTION_DAYS must be >= 0 (0 disables pruning)")
    return days


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only")
    args = parser.parse_args()

    days = retention_days()
    if days == 0:
        logger.info("AUDIT_LOG_RETENTION_DAYS=0 — pruning disabled; exiting")
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with SessionLocal() as db:
        total = db.scalar(select(func.count(AuditLog.id))) or 0
        due = db.scalar(
            select(func.count(AuditLog.id)).where(AuditLog.created_at < cutoff)
        ) or 0
        logger.info(
            "audit_logs: total=%d due_for_prune=%d cutoff=%s retention_days=%d",
            total, due, cutoff.isoformat(), days,
        )
        if args.dry_run:
            logger.info("dry-run: %d row(s) would be purged", due)
            return 0
        result = db.execute(delete(AuditLog).where(AuditLog.created_at < cutoff))
        db.commit()
        logger.info(
            "pruned=%d remaining=%d",
            result.rowcount,
            db.scalar(select(func.count(AuditLog.id))) or 0,
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
