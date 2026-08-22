"""Verify cross-worker shared-Redis behaviour with REAL processes (Stage 07).

The production command runs ``uvicorn --workers 2`` behind one port; the two
workers share Postgres and Redis but have separate memory. Any per-process
state (a fakeredis, an in-memory blacklist) silently multiplies rate limits by
the worker count and lets a token revoked on worker A keep working on worker B.

This script starts **two real uvicorn processes** (one worker each, ports
8101/8102) against the same DATABASE_URL and REDIS_URL and proves, over HTTP:

  1. token blacklist is shared — logout via worker A revokes the refresh token
     on worker B;
  2. brute-force lockout is shared — 5 failed passwords via worker A lock the
     ip+email pair on worker B;
  3. rate limits are shared — flooding via worker A throttles worker B.

Usage (Postgres + Redis required; SQLite + fakeredis will FAIL the checks,
which is the point — per-process state must not pass):

    DATABASE_URL=postgresql+psycopg://... REDIS_URL=redis://... \\
      python scripts/verify_multi_worker_redis.py

Exits 0 only when every check passes; prints SUMMARY lines for CI grepping.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PORT_A, PORT_B = 8101, 8102
BASE_ENV = {
    "DATABASE_URL": os.environ["DATABASE_URL"],
    "REDIS_URL": os.environ["REDIS_URL"],
    "AI_PROVIDER": "mock",
    "EMBEDDING_BACKEND": "hash",
    "STORAGE_BACKEND": "local",
    "PAYMENT_PROVIDER": "mock",
    "EMAIL_PROVIDER": "mock",
    "SECRET_KEY": os.environ.get("SECRET_KEY", "multi-worker-test-secret-key-0123456789"),
    "APP_ENV": "test",
    "SEED_DEMO_ACCOUNTS": "true",
    "COOKIE_SECURE": "false",
    "USE_COOKIE_AUTH": "false",
    "LOG_FORMAT": "text",
    "PYTHONUNBUFFERED": "1",
}


def _http(method: str, port: int, path: str, body: dict | None = None,
          headers: dict | None = None) -> tuple[int, dict]:
    data = None
    headers = {"Content-Type": "application/json", **(headers or {})}
    if body is not None:
        import json

        data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = resp.read()
            return resp.status, _loads(payload)
    except urllib.error.HTTPError as exc:
        return exc.code, _loads(exc.read())


def _loads(raw: bytes) -> dict:
    import json

    try:
        return json.loads(raw)
    except Exception:
        return {"_raw": raw.decode(errors="replace")[:200]}


def _wait_ready(port: int, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status, _ = _http("GET", port, "/api/v1/health/ready")
            if status == 200:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise SystemExit(f"worker on :{port} did not become ready in {timeout}s")


def _login(port: int, email: str, password: str) -> tuple[int, dict]:
    return _http("POST", port, "/api/v1/auth/login",
                 {"email": email, "password": password})


def main() -> int:
    procs: list[subprocess.Popen] = []
    results: list[tuple[str, bool, str]] = []
    try:
        for port in (PORT_A, PORT_B):
            proc = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app.main:app",
                 "--host", "127.0.0.1", "--port", str(port), "--workers", "1"],
                cwd=BACKEND, env={**os.environ, **BASE_ENV},
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            procs.append(proc)
        for port in (PORT_A, PORT_B):
            _wait_ready(port)
        print(f"[setup] workers ready on :{PORT_A} and :{PORT_B}", flush=True)

        email = f"mw-{uuid.uuid4().hex[:8]}@example.com"
        password = "MultiWorkerPass1!"
        status, data = _http("POST", PORT_A, "/api/v1/auth/register",
                             {"email": email, "password": password, "full_name": "MW Test"})
        if status != 201:
            results.append(("register", False, f"status {status}: {data}"))
            _summarise(results)
            return 1
        access_a = data["data"]["access_token"]
        refresh_a = data["data"]["refresh_token"]

        # 1. Blacklist shared: logout on A, refresh on B must fail.
        status, data = _http("POST", PORT_A, "/api/v1/auth/logout",
                             {"refresh_token": refresh_a},
                             headers={"Authorization": f"Bearer {access_a}"})
        if status != 200:
            results.append(("logout-a", False, f"status {status}: {data}"))
        status, _ = _http("POST", PORT_B, "/api/v1/auth/refresh", {"refresh_token": refresh_a})
        results.append((
            "blacklist-shared",
            status == 401,
            f"refresh after logout-on-A via B -> HTTP {status} (expect 401)",
        ))

        # 2. Brute-force lockout shared: 5 wrong passwords via A, correct via B.
        wrong = "WrongPassword1!"
        for _ in range(5):
            _login(PORT_A, email, wrong)
        status, data = _login(PORT_B, email, password)
        results.append((
            "lockout-shared",
            status in (429, 423, 403),
            f"correct password via B after 5 failures via A -> HTTP {status} (expect 429)",
        ))

        # 3. Rate limit shared: burst /recommend via A, expect 429 on B.
        headers_a = {"Authorization": f"Bearer {access_a}"}

        def _recommend(port: int) -> int:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/v1/recommend",
                method="POST", headers={**headers_a, "Content-Type": "application/json"},
                data=(b'{"styles":["scandinavian"],"color_palette":["#FFFFFF"],'
                      b'"materials":["wood"],"patterns":[],'
                      b'"room_width_cm":400,"room_length_cm":500,'
                      b'"budget_min_toman":1000000,"budget_max_toman":50000000}'),
            )
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return resp.status
            except urllib.error.HTTPError as exc:
                return exc.code

        burst = 0
        # RECOMMEND_RATE_LIMIT_PER_MINUTE=20: burst past the limit on A. With a
        # per-process fakeredis this never throttles (each worker has its own
        # counter); with real shared Redis the 21st request returns 429.
        for _ in range(25):
            burst = _recommend(PORT_A)
            if burst == 429:
                break
        status_b = _recommend(PORT_B)
        results.append((
            "rate-limit-shared",
            burst == 429 and status_b == 429,
            f"burst via A -> HTTP {burst}; then via B -> HTTP {status_b} (expect 429/429)",
        ))
    finally:
        for proc in procs:
            proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    _summarise(results)
    return 0 if all(ok for _, ok, _ in results) else 1


def _summarise(results: list[tuple[str, bool, str]]) -> None:
    for name, ok, detail in results:
        print(f"CHECK {name}: {'PASS' if ok else 'FAIL'} — {detail}", flush=True)
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"SUMMARY multi-worker shared-redis: {passed}/{len(results)} checks passed", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
