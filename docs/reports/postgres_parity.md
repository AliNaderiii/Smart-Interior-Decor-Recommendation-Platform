# Postgres + pgvector Parity Report

PM feedback P0-3 resolution. Executed 2026-08-19 against a real PostgreSQL 16
instance with pgvector 0.6.2 (embedded `pgserver` build — same engine and
extension binaries as `ankane/pgvector` in docker-compose).

## 1. Migration creates the extension and HNSW index

```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, initial schema —
      pgvector extension, all tables, hot-path indexes
```

Verified via catalog queries:

```
extension: ('vector', '0.6.2')
index: ix_products_style_embedding
  CREATE INDEX ix_products_style_embedding ON public.products
    USING hnsw (style_embedding vector_cosine_ops)
index: ix_products_filter
  CREATE INDEX ix_products_filter ON public.products
    USING btree (room_type, category, is_verified, price_toman)
```

## 2. Fused Stage A+B pgvector query exercised

`_stage_ab_postgres` (single SQL: hard filter + `ORDER BY style_embedding <=> :emb
LIMIT 100`) returns correct semantics on the seeded catalog:

```
fused pgvector query returned 16 candidates; top style_sim=0.720
top sofa: Light Oak Scandinavian Sofa — Walnut Wood
explain : Style Match 72% | Color Match 100% | Budget Fit 89% | Material: wood (matches your choice)
```

`EXPLAIN` confirms the cosine-distance sort is used:

```
Limit  (cost=8.94..8.98 rows=16 width=41)
  ->  Sort  (cost=8.86..8.90 rows=16 width=41)
        Sort Key: ((products.style_embedding <=> $0))
```

(Planner picks seq-scan+sort at 100 rows — correct; HNSW engages at scale.)

## 3. Full test suite against Postgres

```
DATABASE_URL=postgresql+psycopg://…  pytest tests/
45 passed, 1 warning in 9.04s
```

Same 45/45 result as the SQLite run — the JSONVector fallback and the pgvector
production path are behaviorally equivalent.

## 4. Load test on the Postgres backend

100 concurrent `POST /recommend`, unique payloads, cold cache, uvicorn
2 workers, pool 20+30 overflow:

```
p50=1418ms  p95=1625ms  max=1673ms  mean=1422ms
p95 < 2s : PASS
```

Note: load test executed with `RECOMMEND_RATE_LIMIT_PER_MINUTE=0` (the new
per-user AI-cost limiter would otherwise 429 requests 21+, by design).

## 5. Reproduction

```bash
# CI (GitHub Actions): backend job runs services ankane/pgvector + redis
# and executes alembic upgrade head && pytest — see ci/github-ci.yml.

# Docker:
docker-compose -f docker-compose.yml -f docker-compose.test.yml \
  run --rm backend sh -c "alembic upgrade head && pytest tests/ -v"

# Without Docker (embedded Postgres):
cd backend && python scripts/dev_postgres.py /tmp/pgdev &   # prints DATABASE_URL
DATABASE_URL=... alembic upgrade head && DATABASE_URL=... pytest tests/
```
