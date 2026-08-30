# Container & Infrastructure Security Hygiene Audit

**Audit Date:** 2026-08-28  
**Scope:** `Dockerfile` (backend), `frontend/Dockerfile`, `docker-compose.yml`, `docker-compose.prod.yml`, `Caddyfile`  
**Auditor:** SA-4 (Infrastructure Security Engineer)

---

## 1. Image Pinning & Base Image Integrity

| Component | Base Image / Pinned Tag | Security Assessment |
|---|---|---|
| **Backend Builder** | `python:3.12.9-slim` | Pinned to patch version `3.12.9-slim`. Multi-stage build discards compiler toolchain from final image. |
| **Backend Runtime** | `python:3.12.9-slim` | Minimal slim Debian base; no unnecessary packages. |
| **Frontend Builder** | `node:22.14-alpine` | Pinned to patch version `22.14-alpine`. Build tools (`npm`, `vite`, `tsc`) discarded after compilation. |
| **Frontend Runtime** | `nginx:1.27.4-alpine` | Pinned to patch version `1.27.4-alpine`. Serves static bundle only; 0 build tools in runtime image. |
| **PostgreSQL** | `pgvector/pgvector:0.6.2-pg16` | Pinned to pgvector `0.6.2` on Postgres `16`. |
| **Redis** | `redis:7.4-alpine` | Pinned to minor/patch `7.4-alpine`. Append-only persistence enabled. |
| **Caddy Proxy** | `caddy:2.8-alpine` | Pinned to `2.8-alpine`. TLS 1.3 enforced. |

---

## 2. Non-Root Execution & Privilege Dropping

| Container | User Configuration | Assessment |
|---|---|---|
| **Backend** | `useradd --create-home --shell /usr/sbin/nologin appuser` + `USER appuser` | **PASS** — Application runtime executes strictly as non-root user `appuser` on unprivileged port 8000. |
| **Frontend** | Nginx master starts unprivileged worker processes under user `nginx`. | **PASS** — Static assets served with least privilege. |
| **Postgres / Redis** | Official Alpine/Debian defaults drop privileges to `postgres` (uid 999) and `redis` (uid 999). | **PASS** — Standard non-root database execution. |

---

## 3. Secret Management & Runtime Environment

- **Environment Separation:** Database passwords (`POSTGRES_PASSWORD`), encryption keys (`FERNET_KEY`), JWT secrets (`SECRET_KEY`), and storage credentials are never baked into Docker images.
- **Fail-Safe Startup:** `Settings.validate_runtime()` fails fast on startup in `APP_ENV=production` if weak or default secrets are detected.
- **Resource Limits:** `docker-compose.prod.yml` specifies explicit memory and CPU limits (`memory: 1024M`, `cpus: 2.0` for backend/postgres; `memory: 256M` for redis; `memory: 128M` for frontend/caddy) preventing Denial of Service via host resource starvation.
- **Maintenance Loop:** Isolated maintenance service runs `prune_audit_logs.py` daily to enforce the 180-day GDPR data retention policy.

---

## 4. Verdict

**PASS** — All container images pinned to explicit versions, non-root user execution enforced on application containers, multi-stage builds discard toolchains, and runtime secrets are managed via external environment configuration.
