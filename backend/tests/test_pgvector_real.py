"""Stage 04 · the real PostgreSQL + pgvector path (Stage A+B fused query).

Runs only when ``TEST_DATABASE_URL`` points at PostgreSQL with the pgvector
extension available (``scripts/dev_postgres.py`` provisions one via pgserver).
Skips cleanly otherwise so the default SQLite suite stays hermetic.

What only this file can prove:
* the **migration chain** produces the vector column and the HNSW index;
* a wrong-dimension embedding is rejected by the database, not silently
  truncated;
* ``_stage_ab_postgres`` (the production Stage A+B query) respects the hard
  filters and returns a deterministic order across repeated executions;
* post-filtered ANN recall at the configured ``hnsw.ef_search`` matches the
  exact scan on a >1k-row catalog;
* the query plan is captured (index vs seq scan is a planner decision that
  depends on table size — the authoritative plan evidence at 1k/10k rows is
  captured by ``scripts/bench_pgvector.py`` and stored under
  ``docs/agent-reports/ai-recommender-evidence/``).
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

PG_URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not PG_URL.startswith(("postgres", "postgresql")),
    reason="set TEST_DATABASE_URL to a PostgreSQL+pgvector URL to run",
)

import json  # noqa: E402

from ai.embedding_service import get_embedding  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.services import recommender as rec  # noqa: E402

ROWS = 1_200  # > 1k so the planner faces a real choice


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(PG_URL)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def migrated(engine):
    """Apply the real migration chain, then load a deterministic >1k catalog.

    The schema is dropped first so this module always starts from the
    migration chain itself (the main suite's conftest creates the same tables
    via ``create_all`` without alembic versioning when it shares the server).

    ``alembic/env.py`` resolves its URL from the live ``settings`` object
    (``settings.DATABASE_URL``), so when this module runs inside the full
    suite — main suite on one database, this module on its dedicated one —
    the URL is temporarily pointed at THIS module's database for the duration
    of the alembic commands. Without this, alembic would run against the main
    suite's already-migrated database and crash on ``DuplicateTable``.
    """
    from alembic.config import Config

    from alembic import command

    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    cfg = Config("alembic.ini")
    original_url = settings.DATABASE_URL
    object.__setattr__(settings, "DATABASE_URL", PG_URL)
    try:
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
    finally:
        object.__setattr__(settings, "DATABASE_URL", original_url)
        # env.py runs logging.config.fileConfig(alembic.ini), which disables
        # every logger that existed before it (default
        # disable_existing_loggers=True) — including loggers pytest's caplog
        # relies on for later modules in the same run. Re-enable them so this
        # module cannot break log capture suite-wide.
        import logging

        for logger in logging.Logger.manager.loggerDict.values():
            if isinstance(logger, logging.Logger) and logger.disabled:
                logger.disabled = False
    with engine.begin() as c:
        c.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        c.execute(text("DELETE FROM products WHERE id LIKE 'pgt-%'"))
        rng_seed = 42
        import random

        rng = random.Random(rng_seed)
        cats = ["sofa", "coffee_table", "rug", "lighting", "chair", "storage", "decor"]
        styles = ["modern", "scandinavian", "industrial", "boho", "minimal", "classic"]
        rows = []
        for i in range(ROWS):
            emb = get_embedding(f"pg test product {i} {rng.choice(styles)}")
            rows.append({
                "id": f"pgt-{i:06d}",
                "title": f"PG Test {i}",
                "title_fa": f"محصول تست {i}",
                "category": cats[i % len(cats)],
                "price": rng.randint(1_500_000, 120_000_000),
                "styles": json.dumps([rng.choice(styles)]),
                "emb": "[" + ",".join(f"{x:.6f}" for x in emb) + "]",
                "verified": i % 8 != 0,
            })
        CHUNK = 300
        for start in range(0, len(rows), CHUNK):
            chunk = rows[start:start + CHUNK]
            values = ",".join(
                f"(:i{j}, :t{j}, :tf{j}, :c{j}, 'living_room', :p{j}, "
                f"'https://example.com/x.jpg', '', NULL, '[\"#888888\"]'::json, "
                f"CAST(:s{j} AS json), '[\"wood\"]'::json, '[\"solid\"]'::json, "
                f"180, 90, 75, 0.9, '{{}}'::json, :v{j}, CAST(:e{j} AS vector), now(), now())"
                for j in range(len(chunk))
            )
            params = {}
            for j, r in enumerate(chunk):
                params.update({
                    f"i{j}": r["id"], f"t{j}": r["title"], f"tf{j}": r["title_fa"],
                    f"c{j}": r["category"], f"p{j}": r["price"],
                    f"s{j}": r["styles"], f"v{j}": r["verified"], f"e{j}": r["emb"],
                })
            c.execute(text(
                "INSERT INTO products (id, title, title_fa, category, room_type, "
                "price_toman, image_url, seller_link, seller_link_ok, colors, styles, "
                "materials, patterns, width_cm, depth_cm, height_cm, "
                "extraction_confidence, extraction_raw, is_verified, style_embedding, "
                "created_at, updated_at) VALUES " + values
            ), params)
        c.execute(text("ANALYZE products"))
    return engine


class TestSchema:
    def test_migration_head_creates_vector_column(self, migrated, engine):
        with engine.connect() as c:
            version = c.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert version == "0003"
            col = c.execute(text(
                "SELECT atttypmod FROM pg_attribute a JOIN pg_class r ON a.attrelid = r.oid "
                "WHERE r.relname = 'products' AND a.attname = 'style_embedding'"
            )).scalar_one()
            assert col == 512, "vector column must be vector(512)"

    def test_hnsw_index_exists(self, migrated, engine):
        with engine.connect() as c:
            idx = c.execute(text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE indexname = 'ix_products_style_embedding'"
            )).scalar_one()
            assert "hnsw" in idx and "vector_cosine_ops" in idx

    def test_wrong_dimension_embedding_rejected(self, migrated, engine):
        with pytest.raises(Exception):
            with engine.begin() as c:
                c.execute(text(
                    "INSERT INTO products (id, title, title_fa, category, room_type, "
                    "price_toman, image_url, is_verified, style_embedding, created_at, updated_at) "
                    "VALUES ('bad-dim', 'x', 'x', 'sofa', 'living_room', 100, 'u', true, "
                    "'[0.1,0.2]'::vector, now(), now())"
                ))
        with engine.begin() as c:
            c.execute(text("DELETE FROM products WHERE id = 'bad-dim'"))


class TestStageAB:
    def _session(self, engine):
        from sqlalchemy.orm import sessionmaker

        return sessionmaker(bind=engine)()

    def test_fused_query_respects_hard_filters(self, migrated, engine):
        db = self._session(engine)
        try:
            emb = get_embedding("modern style living room furniture")
            lo, hi = 10_000_000, 60_000_000
            pairs = rec._stage_ab_postgres(db, "sofa", lo, hi, emb)
            assert pairs, "expected candidates in a wide window"
            for product, _sim in pairs:
                assert product.category == "sofa"
                assert product.is_verified
                assert lo <= product.price_toman <= hi
        finally:
            db.close()

    def test_fused_query_is_deterministic_across_runs(self, migrated, engine):
        db = self._session(engine)
        try:
            emb = get_embedding("determinism probe scandinavian wood")
            ids_a = [p.id for p, _ in rec._stage_ab_postgres(db, "sofa", 0, 10**9, emb)]
            ids_b = [p.id for p, _ in rec._stage_ab_postgres(db, "sofa", 0, 10**9, emb)]
            assert ids_a == ids_b, "identical query must return identical order"
        finally:
            db.close()

    def test_recall_matches_exact_scan_at_configured_ef(self, migrated, engine):
        db = self._session(engine)
        try:
            emb = get_embedding("recall probe industrial metal sofa")
            ann = {p.id for p, _ in rec._stage_ab_postgres(db, "sofa", 0, 10**9, emb)}
            exact_rows = db.execute(text(
                "SELECT id FROM products WHERE room_type='living_room' "
                "AND category='sofa' AND is_verified "
                "AND style_embedding IS NOT NULL "
                "ORDER BY style_embedding <=> CAST(:e AS vector), id LIMIT 100"
            ), {"e": "[" + ",".join(f"{x:.6f}" for x in emb) + "]"}).fetchall()
            exact = {r[0] for r in exact_rows}
            assert exact, "expected exact-scan candidates"
            recall = len(ann & exact) / len(exact)
            assert recall >= 0.95, f"ANN recall {recall:.3f} < 0.95 at ef_search={settings.HNSW_EF_SEARCH}"
        finally:
            db.close()

    def test_no_result_window_returns_empty_quickly(self, migrated, engine):
        db = self._session(engine)
        try:
            emb = get_embedding("no result probe")
            pairs = rec._stage_ab_postgres(db, "sofa", 1, 10, emb)
            assert pairs == []
        finally:
            db.close()

    def test_query_plan_is_captured(self, migrated, engine):
        """Plan node types recorded as evidence; the size-dependent index-vs-seq
        decision is asserted in the bench evidence, not here."""
        emb = "[" + ",".join(f"{x:.6f}" for x in get_embedding("plan probe modern")) + "]"
        plan = "\n".join(
            r[0] for r in engine.connect().execute(text(
                "EXPLAIN (COSTS) SELECT id FROM products "
                "WHERE room_type='living_room' AND category='sofa' AND is_verified "
                "AND price_toman BETWEEN 1000000 AND 150000000 "
                "AND style_embedding IS NOT NULL "
                f"ORDER BY style_embedding <=> '{emb}'::vector, id LIMIT 100"
            )).fetchall()
        )
        assert "ORDER BY" in plan or "Sort" in plan or "hnsw" in plan.lower()
        print(f"\n--- stage A+B plan at {ROWS} rows ---\n{plan}")
