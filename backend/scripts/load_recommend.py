#!/usr/bin/env python
"""End-to-end /recommend load harness — cold & warm p50/p95/p99 evidence.

Stage 2, T-2.2 (contract gate: /recommend p95 < 2 s). Complements
``bench_pgvector.py`` (DB-level): this script measures the FULL HTTP path —
auth, rate-limit check, cache lookup, the fused pgvector query, scoring,
orjson serialization — against a *running* backend.

Methodology (SA-7-reviewed):
  * COLD cell: every request posts a unique inline quiz payload, so the cache
    key ``rec:{user}:{sha}`` never hits. Measures the pgvector + scoring path.
  * WARM cell: a single payload is primed once, then repeated; every sample is
    a Redis (or fakeredis) cache hit. The priming request is excluded.
  * >= samples-per-cell requests per cell (default 200), fixed concurrency,
    monotonic-clock wall time per request, failures counted and never dropped
    silently — any non-200 fails the run.
  * Percentiles use the nearest-rank method on the sorted sample.

Requires: RECOMMEND_RATE_LIMIT_PER_MINUTE=0 on the target backend (the
documented load-test switch — config.py:95); a seeded catalog.

Usage:
    python scripts/load_recommend.py --base-url http://127.0.0.1:8000 \
        --samples 200 --concurrency 20 --json out.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import statistics
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

STYLES = ["modern", "minimal", "scandinavian", "boho", "industrial", "classic"]
PALETTES = [["#2E2E2E", "#FFFFFF"], ["#F2E8D5"], ["#FFFFFF", "#EDEDED"], []]
MATERIALS = [["wood"], ["metal"], ["fabric", "wood"], []]


def make_payload(i: int) -> dict:
    """Deterministic but distinct payloads -> distinct cache keys."""
    return {
        "styles": [STYLES[i % len(STYLES)]],
        "color_palette": PALETTES[i % len(PALETTES)],
        "room_width_cm": 300 + (i % 37) * 10,
        "room_length_cm": 400 + (i % 23) * 10,
        "budget_min_toman": 1_000_000,
        "budget_max_toman": 150_000_000 - (i % 50) * 100_000,
        "materials": MATERIALS[i % len(MATERIALS)],
        "patterns": [],
    }


def pct(vals: list[float], q: float) -> float:
    s = sorted(vals)
    return s[min(len(s) - 1, max(0, round(q * (len(s) - 1))))]


def summarize(lat: list[float]) -> dict:
    return {
        "n": len(lat),
        "mean_ms": round(statistics.fmean(lat), 1),
        "p50_ms": round(pct(lat, 0.50), 1),
        "p95_ms": round(pct(lat, 0.95), 1),
        "p99_ms": round(pct(lat, 0.99), 1),
        "max_ms": round(max(lat), 1),
    }


async def run_cell(client: httpx.AsyncClient, token: str, n: int,
                   concurrency: int, warm_payload: dict | None) -> dict:
    """warm_payload=None -> cold cell (unique payload per request)."""
    sem = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    errors: list[str] = []

    async def one(i: int) -> None:
        body = warm_payload if warm_payload is not None else make_payload(i)
        async with sem:
            t0 = time.perf_counter()
            r = await client.post("/api/v1/recommend", json=body,
                                  headers={"Authorization": f"Bearer {token}"})
            dt = (time.perf_counter() - t0) * 1000.0
        if r.status_code == 200:
            latencies.append(dt)
        else:
            errors.append(f"{r.status_code}: {r.text[:200]}")

    await asyncio.gather(*(one(i) for i in range(n)))
    out = summarize(latencies) if latencies else {"n": 0}
    out["errors"] = len(errors)
    out["error_samples"] = errors[:5]
    return out


def _demo_homeowner() -> tuple[str, str]:
    """The seeded homeowner's credentials, read from their single source.

    tests/test_demo_seeding.py asserts the demo passwords appear in exactly one
    module - a second copy is how an earlier fix got undone - so this imports
    from app.core.demo_seed rather than repeating the literal here.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.core.demo_seed import DEMO_ACCOUNTS
    for account in DEMO_ACCOUNTS:
        if account.role == "homeowner":
            return account.email, account.password
    raise RuntimeError("no seeded homeowner account found in DEMO_ACCOUNTS")


def _report(msg: str, level: str = "error") -> None:
    """Report a harness failure through every channel that survives.

    Raw step logs and job artifacts cannot be downloaded from the supervising
    sandbox, and annotations are capped per check-run and can be dropped. The
    step summary is a separate, reliable channel - run #5 exited 2 with the
    detail annotation missing, which is what motivated this.
    """
    print(f"::{level} title=load-harness::{msg}", flush=True)
    print(f"[load-harness/{level}] {msg}", file=sys.stderr, flush=True)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        try:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(f"\n**load-harness {level}:** {msg}\n")
        except OSError:
            pass


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--samples", type=int, default=200)
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--gate-cold-ms", type=float, default=2000.0,
                    help="Cold cell p95 threshold in milliseconds (default: 2000)")
    ap.add_argument("--gate-warm-ms", type=float, default=2000.0,
                    help="Warm cell p95 threshold in milliseconds (default: 2000)")
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args()

    async with httpx.AsyncClient(base_url=args.base_url, timeout=60.0) as client:
        email = f"loadtest-{uuid.uuid4().hex[:10]}@example.com"
        password = "LoadTest-Passw0rd!"
        r = await client.post("/api/v1/auth/register", json={
            "email": email, "password": password, "role": "homeowner",
            "full_name": "Load Test"})
        # /register is rate limited to 3/min per IP (A07). On a CI runner every
        # job shares one IP, so a burst of runs exhausts it and the harness dies
        # before measuring anything. The seeded demo homeowner is equivalent for
        # a latency measurement, so fall back to it rather than failing the
        # contract gate on an anti-abuse control that is working correctly.
        if r.status_code == 429:
            _report("register rate-limited (429) - falling back to the demo account",
                    level="notice")
            email, password = _demo_homeowner()
        if r.status_code not in (200, 201, 429):
            _report(f"register failed: HTTP {r.status_code} "
                    f"{r.text[:400]}".replace("\n", " "))
            return 2
        r = await client.post("/api/v1/auth/login",
                              json={"email": email, "password": password})
        if r.status_code != 200:
            _report(f"login failed for {email}: HTTP {r.status_code} "
                    f"{r.text[:400]}".replace("\n", " "))
            return 2
        # Envelope: {"success": true, "data": {..., "access_token": ...}}
        token = r.json()["data"]["access_token"]

        # --- COLD cell -----------------------------------------------------
        cold = await run_cell(client, token, args.samples, args.concurrency, None)

        # --- WARM cell -----------------------------------------------------
        warm_payload = make_payload(0)
        prime = await client.post("/api/v1/recommend", json=warm_payload,
                                  headers={"Authorization": f"Bearer {token}"})
        if prime.status_code != 200:
            print(f"warm prime failed: {prime.status_code}", file=sys.stderr)
            return 2
        warm = await run_cell(client, token, args.samples, args.concurrency,
                              warm_payload)

    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                         text=True).stdout.strip()
    cold_pass = cold.get("p95_ms", 1e9) < args.gate_cold_ms and not cold["errors"]
    warm_pass = warm.get("p95_ms", 1e9) < args.gate_warm_ms and not warm["errors"]
    result = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "commit": sha,
        "base_url": args.base_url,
        "samples_per_cell": args.samples,
        "concurrency": args.concurrency,
        "host": {
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "python": platform.python_version(),
        },
        "cold": cold,
        "warm": warm,
        "gate": {
            "gate_cold_ms": args.gate_cold_ms,
            "gate_warm_ms": args.gate_warm_ms,
            "cold_pass": cold_pass,
            "warm_pass": warm_pass,
        },
    }
    print(json.dumps(result, indent=2))
    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(result, f, indent=2)
    # Annotation-readable summary: the supervising sandbox cannot download CI
    # artifacts (Azure blob egress blocked); check-run annotations are the
    # only machine-readable channel back.
    compact = (
        f"n={args.samples}/cell conc={args.concurrency} | "
        f"cold p50={cold.get('p50_ms')} p95={cold.get('p95_ms')} "
        f"p99={cold.get('p99_ms')} err={cold['errors']} | "
        f"warm p50={warm.get('p50_ms')} p95={warm.get('p95_ms')} "
        f"p99={warm.get('p99_ms')} err={warm['errors']} | "
        f"gate_cold<{args.gate_cold_ms:.0f}ms cold_pass={cold_pass} "
        f"gate_warm<{args.gate_warm_ms:.0f}ms warm_pass={warm_pass}"
    )
    print(f"::notice title=p95-cells::{compact}")
    ok = cold_pass and warm_pass
    return 0 if ok else 1


if __name__ == "__main__":
    # Run #4 lesson: this script exited 2 with no annotation at all, which
    # means it died before reaching the instrumented register/login checks.
    # Step logs are unreadable from the agent sandbox, so an uninstrumented
    # exit is undiagnosable. Nothing may fail silently from here on.
    try:
        _rc = asyncio.run(main())
    except BaseException as exc:  # noqa: BLE001 - deliberate: report, then re-raise
        import traceback
        _tb = traceback.format_exc().replace("\n", " ")[-700:]
        print(f"::error title=load-harness-crashed::"
              f"{type(exc).__name__}: {exc} | {_tb}")
        raise
    if _rc != 0:
        print(f"::error title=load-harness-exit::exit code {_rc}")
    raise SystemExit(_rc)
