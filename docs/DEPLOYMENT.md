# Deployment Guide

## 0. One-command local / VPS bring-up

```bash
cp .env.example .env
# fill: SECRET_KEY (openssl rand -hex 32), FERNET_KEY, POSTGRES_PASSWORD,
#       AI_PROVIDER + key, S3_* if using object storage
docker-compose up --build
```

Services: `postgres` (ankane/pgvector), `redis`, `backend` (runs
`alembic upgrade head` + idempotent seed on boot), `frontend` (nginx),
`caddy` (TLS 1.3, ports 80/443). App: `https://<host>/`, API docs: `/docs`.

## 1. Production checklist

- [ ] `.env`: strong `SECRET_KEY`, `FERNET_KEY`, DB password; `APP_ENV=production`
- [ ] Caddyfile: replace `:443` with your domain → automatic Let's Encrypt,
      remove `tls internal` (keep the `protocols tls1.3 tls1.3` block)
- [ ] `STORAGE_BACKEND=s3` with Arvan/Liara credentials
- [ ] `PAYMENT_PROVIDER=zarinpal` + real `ZARINPAL_MERCHANT_ID` +
      `PAYMENT_CALLBACK_URL=https://yourdomain/upgrade`
- [ ] `AI_PROVIDER=gemini` (or `openai`) with API key; optionally
      `EMBEDDING_BACKEND=clip` (uncomment torch/sentence-transformers in
      `backend/requirements.txt`; first boot downloads ~600 MB)
- [ ] Seed with real CLIP vectors: `python backend/scripts/seed_products.py --real-embeddings`
      (or `--from-json` if `backend/seed_data/embeddings_real.json` is committed)
- [ ] Validate real extraction quality: `python backend/scripts/evaluate_extraction.py --real --sample 10`
- [ ] Run `python scripts/check_links.py --report docs/reports/links.json` after seeding real catalog
- [ ] Enable CI if not yet active: `./scripts/enable_ci.sh` (needs a token with `workflow` scope)
- [ ] Postgres volume on encrypted disk; scheduled `pg_dump` backups

## 2. Deploy to a VPS / EC2

```bash
ssh user@server
git clone <repo> && cd Smart-Interior-Decor-Recommendation-Platform
cp .env.example .env && $EDITOR .env      # see checklist
docker compose up --build -d
docker compose logs -f backend            # wait for "Application startup complete"
```

Point DNS A-record at the server; Caddy handles certificates automatically.

## 3. Deploy to Liara

1. Create a **PostgreSQL** database (enable `vector` extension from the Liara
   panel or `CREATE EXTENSION vector;`) and a **Redis** instance.
2. Backend: `liara deploy --app decor-api --platform docker` from `backend/`
   (Dockerfile is multi-stage, port 8000). Set env vars from `.env.example`.
3. Frontend: `liara deploy --app decor-web --platform static` after
   `npm run build` (upload `dist/`), or use the frontend Dockerfile.
4. Set `FRONTEND_ORIGIN` on the backend and point the frontend's `/api` proxy
   (Liara "reverse proxy" feature or an edge worker) at `decor-api`.
5. Object storage: create a Liara bucket, set `STORAGE_BACKEND=s3`,
   `S3_ENDPOINT=https://storage.iran.liara.space`, bucket + keys.

## 4. Deploy to ArvanCloud

Same shape: Arvan Managed Postgres (or a pgvector container in Arvan IaaS),
Arvan Object Storage (`S3_ENDPOINT=https://s3.ir-thr-at1.arvanstorage.ir`),
containers via Arvan PaaS or a compute instance running docker-compose.
Put Arvan CDN in front of the frontend for asset caching in-country.

## 5. Migrations

```bash
docker compose exec backend alembic upgrade head      # apply
docker compose exec backend alembic revision --autogenerate -m "…"
```

## 6. Ops runbook

| Symptom | Action |
|---|---|
| `/recommend` slow | check Redis up (`docker compose exec redis redis-cli ping`); verify HNSW index exists (`\di+ ix_products_style_embedding`) |
| pgvector missing | `docker compose exec postgres psql -U decor -c "CREATE EXTENSION IF NOT EXISTS vector"` then re-run migrations |
| dead seller links | `python scripts/check_links.py` (sets `seller_link_ok`, UI shows red dot) |
| rotate JWT secret | change `SECRET_KEY`, restart backend — all sessions invalidated by design |

## 7. Security posture (acceptance criteria mapping)

| Criterion | Where |
|---|---|
| TLS 1.3 all endpoints | `Caddyfile` (`protocols tls1.3 tls1.3`, HTTP→HTTPS redirect, HSTS) |
| bcrypt passwords | `app/core/security.py` (passlib, `$2b$`) |
| Encryption at rest | `KMSClient` Fernet abstraction + provider disk encryption |
| GDPR deletion | `DELETE /api/v1/users/me` hard delete, tested |
| No payment data | `payments` table stores authority/ref_id only |
| JWT 15 min / 7 d + blacklist | `app/core/security.py`, `app/api/routes/auth.py` |
| No secrets in repo | all via `.env`; `.env` gitignored; `.env.example` documented |
