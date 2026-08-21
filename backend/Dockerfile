# ---- Stage 1: build locked dependency wheels ----
FROM python:3.12.9-slim AS builder
WORKDIR /build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
COPY requirements.lock.txt ./
RUN python -m pip wheel --wheel-dir /wheels -r requirements.lock.txt

# ---- Stage 2: minimal non-root runtime ----
FROM python:3.12.9-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

COPY --from=builder /wheels /wheels
COPY requirements.lock.txt ./
RUN python -m pip install --no-index --find-links=/wheels -r requirements.lock.txt \
    && rm -rf /wheels

COPY . .

# The API and maintenance image never run as root. The official container
# orchestrator may still need root for port binding; the application process is
# always appuser and listens on the unprivileged container port 8000.
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--no-server-header", "--proxy-headers"]
