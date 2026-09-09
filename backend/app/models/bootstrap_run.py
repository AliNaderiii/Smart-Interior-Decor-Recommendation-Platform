"""bootstrap_runs — the durable record of what a container boot did (ADR-017).

``scripts/entrypoint.py`` is the only thing that runs on a shell-less PaaS
(Render free tier and the like): there is no pre-deploy hook, no console and
no editable start command. Every data operation it performs therefore has to
be *idempotent by record*, not by operator memory:

* a labelled catalog replacement (``CATALOG_BOOTSTRAP=replace@<label>``) may
  run **once per label per database** — the unique ``label`` column is the
  lock, so a redeploy, a rollback or a second replica can never wipe the
  catalog a second time;
* every write the entrypoint makes (``catalog_replace``, ``catalog_if_empty``)
  is kept with its before/after counts, because the platform's deploy log
  scrolls away and an operator asking "when did this database last get
  reseeded, and what did it delete?" deserves an answer from the database.

Deliberately **not** ``audit_logs``: that table is pruned on a retention
window (``scripts/prune_audit_logs.py``), and a once-only marker that expires
is not a marker.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPk, utcnow

ACTION_CATALOG_REPLACE = "catalog_replace"
ACTION_CATALOG_IF_EMPTY = "catalog_if_empty"


class BootstrapRun(Base, UUIDPk):
    __tablename__ = "bootstrap_runs"

    #: Operator-chosen label of a once-only operation (``replace@<label>``).
    #: ``NULL`` for unlabelled runs (``if-empty`` loads), which may repeat.
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    #: Human-readable summary (counts before/after, dataset, policy). Never secrets.
    detail: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        # The once-per-label guarantee. NULL labels do not collide (SQL semantics),
        # which is exactly right for the repeatable if-empty action.
        Index("ix_bootstrap_runs_label", "label", unique=True),
    )
