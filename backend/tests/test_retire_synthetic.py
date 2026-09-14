"""``scripts/retire_synthetic.py`` — the last step of the P4-B cut-over.

Runs against the suite database (seeded with the 100 synthetic rows by
``conftest``), so every test restores what it changes.

Contract pinned here:

* selection = the integrity gate's ``is_synthetic`` predicate (``source`` and
  the realistic-dataset marker), optionally narrowed by ``--source``;
* the coverage guard refuses (exit 1, nothing written) while a category would
  keep fewer than ``--min-real`` recommendable real rows;
* dry-run is the default (exit 0, nothing written, plan printed);
* ``--yes`` unverifies (never deletes) the targets, records one audit row and
  flushes the recommendation cache; the rows stay in the table;
* ``--delete`` refuses while a moodboard still references a target unless
  ``--force``;
* ``--check-db`` preflights without importing the engine.
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import delete, select

from ai.embedding_service import get_embedding
from app.models.audit_log import ACTION_PRODUCT_UNVERIFY, ACTION_SYNTHETIC_RETIRE, AuditLog
from app.models.moodboard import Moodboard
from app.models.product import CATEGORIES, Product
from app.models.user import User
from scripts import retire_synthetic as cli


def _real(category: str, n: int) -> list[Product]:
    rows = []
    for i in range(n):
        rows.append(Product(
            id=uuid.uuid4().hex, title=f"Real {category} {i}", title_fa=f"واقعی {i}",
            category=category, room_type="living_room", price_toman=5_000_000 + i,
            image_url="https://statics.example.com/x.jpg",
            seller_link="https://basalam.com/v/product/1", is_verified=True, integrity_ok=True,
            source="basalam", source_product_id=f"r-{i}", styles=["modern"], colors=["#2E2E2E"],
            materials=["fabric"], patterns=["solid"], style_embedding=get_embedding(f"real {category} {i}"),
        ))
    return rows


@pytest.fixture()
def real_catalog(db):
    """Three recommendable real rows per category, removed afterwards."""
    rows = [r for c in CATEGORIES for r in _real(c, 3)]
    db.add_all(rows)
    db.commit()
    ids = [r.id for r in rows]
    yield rows
    db.execute(delete(Product).where(Product.id.in_(ids)))
    db.commit()


@pytest.fixture()
def restore_verified(db):
    """Whatever a test unverifies is verified again for the rest of the suite."""
    before = {r.id: r.is_verified for r in db.scalars(select(Product))}
    yield
    db.expire_all()
    for row in db.scalars(select(Product)):
        if row.id in before and row.is_verified != before[row.id]:
            row.is_verified = before[row.id]
    db.commit()


class TestSelection:
    def test_synthetic_rows_are_selected_by_the_gate_predicate(self, db):
        rows = list(db.scalars(select(Product)))
        targets = cli.select_targets(rows, [])
        assert targets and all(r.source == "synthetic-demo" for r in targets)
        assert {r.id for r in targets} == {r.id for r in rows if r.source in ("synthetic-demo", "perf")}

    def test_source_filter_narrows(self, db):
        rows = list(db.scalars(select(Product)))
        assert cli.select_targets(rows, ["perf"]) == []
        assert len(cli.select_targets(rows, ["synthetic-demo"])) == len(cli.select_targets(rows, []))

    def test_realistic_dataset_marker_counts_as_synthetic(self):
        class Row:
            source = "manual"
            extraction_raw = {"source": "realistic_dataset_v3"}

        row = Row()
        assert cli.select_targets([row], []) == [row]
        assert cli.select_targets([row], ["synthetic-demo"]) == []  # narrowed by source value


class TestCoverageGuard:
    def test_refuses_without_real_rows(self, db, capsys):
        code = cli.main([])
        out = capsys.readouterr().out
        assert code == cli.EXIT_REFUSED
        assert "REFUSED" in out and "thin" in out
        # nothing written
        assert db.scalar(select(Product).where(Product.source == "synthetic-demo",
                                               Product.is_verified.is_(True))) is not None

    def test_plan_reports_per_category(self, db, real_catalog):
        rows = list(db.scalars(select(Product)))
        targets = cli.select_targets(rows, [])
        report = cli.plan(rows, targets, list(CATEGORIES), 3)
        assert report["ok"] is True and report["thin_categories"] == []
        for c in CATEGORIES:
            assert report["per_category"][c]["real_recommendable"] >= 3
            assert report["per_category"][c]["synthetic"] >= 1

    def test_min_real_can_be_raised(self, db, real_catalog, capsys):
        assert cli.main(["--min-real", "4"]) == cli.EXIT_REFUSED
        assert "REFUSED" in capsys.readouterr().out


class TestDryRunAndApply:
    def test_dry_run_writes_nothing(self, db, real_catalog, capsys, tmp_path):
        report = tmp_path / "plan.json"
        code = cli.main(["--report", str(report)])
        out = capsys.readouterr().out
        assert code == cli.EXIT_OK and "dry-run: nothing written" in out
        db.expire_all()
        verified_synthetic = db.scalar(
            select(Product).where(Product.source == "synthetic-demo", Product.is_verified.is_(True)))
        assert verified_synthetic is not None
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["dry_run"] is True and data["mode"] == "unverify" and data["ok"] is True

    def test_yes_unverifies_audits_and_flushes(self, db, real_catalog, restore_verified, capsys, tmp_path):
        from app.core.redis_client import get_redis

        get_redis().set("rec:u:deadbeef", "x")
        before = db.scalar(select(AuditLog.id).where(AuditLog.action == ACTION_PRODUCT_UNVERIFY)
                           .order_by(AuditLog.created_at.desc()))
        report = tmp_path / "done.json"
        code = cli.main(["--yes", "--report", str(report)])
        out = capsys.readouterr().out
        assert code == cli.EXIT_OK and "done: unverify" in out
        db.expire_all()
        synthetic = list(db.scalars(select(Product).where(Product.source == "synthetic-demo")))
        assert synthetic, "soft retire must keep the rows"
        assert not any(r.is_verified for r in synthetic)
        real = list(db.scalars(select(Product).where(Product.source == "basalam")))
        assert all(r.is_verified for r in real)
        last = db.scalar(select(AuditLog).where(AuditLog.action == ACTION_PRODUCT_UNVERIFY)
                         .order_by(AuditLog.created_at.desc()))
        assert last is not None and last.id != before and "retire_synthetic" in last.detail
        assert get_redis().get("rec:u:deadbeef") is None
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["changed"] == len(synthetic) and data["dry_run"] is False

    def test_apply_is_idempotent(self, db, real_catalog, restore_verified, capsys):
        assert cli.main(["--yes"]) == cli.EXIT_OK
        assert cli.main(["--yes"]) == cli.EXIT_OK
        assert "done: unverify 0 rows" in capsys.readouterr().out

    def test_category_narrowing(self, db, real_catalog, restore_verified, capsys):
        assert cli.main(["--yes", "--category", "rug"]) == cli.EXIT_OK
        db.expire_all()
        rugs = list(db.scalars(select(Product).where(Product.source == "synthetic-demo", Product.category == "rug")))
        sofas = list(db.scalars(select(Product).where(Product.source == "synthetic-demo", Product.category == "sofa")))
        assert rugs and not any(r.is_verified for r in rugs)
        assert any(s.is_verified for s in sofas)


class TestDelete:
    def test_delete_refuses_while_referenced(self, db, real_catalog, capsys):
        user = db.scalar(select(User))
        target = db.scalar(select(Product).where(Product.source == "synthetic-demo"))
        board = Moodboard(user_id=user.id, title="ref", items=[{"product_id": target.id, "x": 0, "y": 0, "w": 1, "h": 1}])
        db.add(board)
        db.commit()
        try:
            code = cli.main(["--delete", "--yes"])
            out = capsys.readouterr().out
            assert code == cli.EXIT_REFUSED and "still referenced" in out
            db.expire_all()
            assert db.get(Product, target.id) is not None
        finally:
            db.delete(board)
            db.commit()

    def test_force_flag_requires_delete(self):
        with pytest.raises(SystemExit) as exc:
            cli.main(["--force"])
        assert exc.value.code == 2

    def test_delete_action_constant_is_distinct(self):
        assert ACTION_SYNTHETIC_RETIRE == "synthetic_retire"
        assert ACTION_SYNTHETIC_RETIRE != ACTION_PRODUCT_UNVERIFY


class TestCheckDb:
    def test_check_db_prints_target_without_secret(self, capsys):
        code = cli.main(["--check-db"])
        out = capsys.readouterr().out
        assert code == cli.EXIT_OK
        assert out.startswith("database: ")
        assert "://" not in out.split("(")[0] or "@" not in out
