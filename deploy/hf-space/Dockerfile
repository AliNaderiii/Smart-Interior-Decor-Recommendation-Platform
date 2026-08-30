# =============================================================================
# Public demo container — one image, all services   [Stage 4, Wave 2 / N1]
# =============================================================================
# Target: a FREE Hugging Face Docker Space (2 vCPU / 16 GB, shared CPU).
# A Space runs exactly ONE container, so PostgreSQL 16 + pgvector, Redis, the
# FastAPI backend and the built SPA all live here under supervisord.
#
# This is a DEMO box, not the production topology:
#   * storage is EPHEMERAL — the database is recreated and re-seeded on every
#     restart (deviation D-4a, accepted by the supervisor);
#   * AI is mocked and payments are Zarinpal sandbox (no credentials anywhere);
#   * the three demo accounts exist ON PURPOSE, with the production refusal
#     re-proven at boot by entrypoint.sh;
#   * interactive API docs are FORCED OFF via API_DOCS_MODE=disabled
#     (D-4.1 condition — an explicit switch, never an env default).
#
# The production topology (separate containers, Caddy, TLS, S3) is unchanged
# and stays in docker-compose.prod.yml for Stage 5.
#
# BUILD CONTEXT: the repository root.
#   docker build -f deploy/hf-space/Dockerfile -t decor-demo .
#
# SIZE: see deploy/hf-space/README-dev.md for the measured/estimated breakdown.
# =============================================================================

# ---- Stage 1: build the SPA -------------------------------------------------
# Identical toolchain to frontend/Dockerfile (node:22.14-alpine, npm ci,
# npm run build), so the CI `frontend` and `docker` jobs already exercise this
# exact build. The only difference is the brand build-args (T-4.4).
FROM node:22.14-alpine AS frontend-builder
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ARG VITE_BRAND_NAME="Smart Decor"
ARG VITE_BRAND_COLOR=""
ARG VITE_BRAND_LOGO_URL=""
ENV VITE_BRAND_NAME=$VITE_BRAND_NAME \
    VITE_BRAND_COLOR=$VITE_BRAND_COLOR \
    VITE_BRAND_LOGO_URL=$VITE_BRAND_LOGO_URL
RUN npm run build

# ---- Stage 2: build the Python wheels ---------------------------------------
# Same lockfile and same wheel-build step as backend/Dockerfile, so the CI
# `backend` and `docker` jobs already prove this resolves and installs.
FROM python:3.12.9-slim AS python-builder
WORKDIR /build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
COPY backend/requirements.lock.txt ./
RUN python -m pip wheel --wheel-dir /wheels -r requirements.lock.txt

# ---- Stage 3: the runtime ---------------------------------------------------
FROM python:3.12.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    PGDATA=/data/pgdata \
    PATH="/usr/lib/postgresql/16/bin:${PATH}"

# PostgreSQL 16 + pgvector, Redis, nginx and supervisord.
# pgvector comes from PGDG (Debian trixie ships PG17, and the project pins 16
# to match docker-compose.yml and every CI job).
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg lsb-release; \
    install -d /usr/share/postgresql-common/pgdg; \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc; \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        postgresql-16 postgresql-16-pgvector \
        redis-server \
        nginx \
        supervisor \
        gosu; \
    apt-get purge -y --auto-remove gnupg lsb-release; \
    rm -rf /var/lib/apt/lists/* /var/log/* /usr/share/doc /usr/share/man

# ---- Python dependencies ----
COPY --from=python-builder /wheels /wheels
COPY backend/requirements.lock.txt /tmp/requirements.lock.txt
RUN python -m pip install --no-index --find-links=/wheels -r /tmp/requirements.lock.txt \
    && rm -rf /wheels /tmp/requirements.lock.txt

# ---- Application ----
WORKDIR /app
COPY backend/ /app/
COPY --from=frontend-builder /build/dist /srv/www

# ---- Service configuration ----
COPY deploy/hf-space/supervisord.conf /etc/supervisor/supervisord.conf
COPY deploy/hf-space/nginx.conf        /etc/nginx/nginx.conf
COPY deploy/hf-space/entrypoint.sh     /usr/local/bin/entrypoint.sh
COPY deploy/hf-space/demo_env.py       /usr/local/bin/demo_env.py
RUN chmod +x /usr/local/bin/entrypoint.sh

# HF Spaces run the container as UID 1000 and mount nothing persistent.
# Every writable path must therefore be owned by that user at build time.
RUN set -eux; \
    useradd -m -u 1000 -s /bin/bash demo || true; \
    install -d -o demo -g demo \
        /data /data/pgdata /data/redis /data/media /data/logs \
        /var/log/supervisor /var/lib/nginx /var/log/nginx /run; \
    chown -R demo:demo /app /srv/www /data /var/log/supervisor \
        /var/lib/nginx /var/log/nginx /run

# The Space's app_port (README.md front-matter) must match this.
EXPOSE 7860

# Demo profile. Anything secret is injected by the deploy workflow as a Space
# secret — nothing sensitive is baked into the image.
ENV APP_ENV=development \
    API_DOCS_MODE=disabled \
    SEED_DEMO_ACCOUNTS=true \
    AI_PROVIDER=mock \
    EMBEDDING_BACKEND=hash \
    STORAGE_BACKEND=local \
    EMAIL_PROVIDER=mock \
    PAYMENT_PROVIDER=zarinpal_sandbox \
    LOCAL_STORAGE_DIR=/data/media \
    DATABASE_URL=postgresql+psycopg://decor:decor@127.0.0.1:5432/decor \
    REDIS_URL=redis://127.0.0.1:6379/0 \
    LOG_FORMAT=text \
    COOKIE_SECURE=true \
    COOKIE_SAMESITE=lax \
    USE_COOKIE_AUTH=true \
    HNSW_EF_SEARCH=400 \
    PORT=7860

USER demo
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=5 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-7860}/api/v1/health/ready" || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
