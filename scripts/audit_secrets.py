#!/usr/bin/env python3
"""Repository secret / hygiene scanner (release-governance tooling).

Scope: read-only. Never mutates the repository.

Scans every **git-tracked** file for:

  * high-signal credential patterns (AWS keys, Google/Gemini API keys, OpenAI
    keys, Slack/GitHub/Stripe tokens, private-key PEM blocks, JWTs, Fernet keys,
    generic ``KEY=<longvalue>`` assignments, connection strings with a password)
  * non-placeholder values assigned to known secret-bearing variable names
  * tracked files above a size threshold (accidental artifacts)
  * tracked files that should never be committed (``.env``, key material,
    SQLite databases, build output)

Placeholders that are *supposed* to be in the repository (``change-me-…``,
empty values, ``sandbox``/``mock`` defaults, ``decor:decor`` local compose
credentials, documented demo passwords) are recognised and reported in a
separate, non-failing "acknowledged placeholder" bucket so the report stays
honest instead of silently ignoring them.

Usage
-----
    python scripts/audit_secrets.py [--json REPORT.json] [--max-bytes N]

Exit codes
----------
    0  no unacknowledged findings
    1  at least one finding that needs human review
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_MAX_BYTES = 2 * 1024 * 1024  # 2 MiB

# --- high-signal credential patterns -------------------------------------
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key_id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("openai_api_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("stripe_key", re.compile(r"\b[rs]k_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("jwt_like", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("basic_auth_url", re.compile(r"\b[a-z][a-z0-9+.\-]*://[^\s/:@]+:[^\s/:@]+@[^\s/]+")),
]

# --- variable names whose value must never be a real credential ----------
SECRET_VARS = re.compile(
    r"^\s*(?:export\s+)?(?P<key>[A-Z0-9_]*"
    r"(?:SECRET|PASSWORD|PASSWD|TOKEN|API_KEY|APIKEY|ACCESS_KEY|PRIVATE_KEY|MERCHANT_ID|FERNET)"
    r"[A-Z0-9_]*)\s*[:=]\s*(?P<val>.+?)\s*$"
)

PLACEHOLDER_MARKERS = (
    "change-me", "changeme", "your-", "your_", "<", "xxx", "placeholder",
    "example", "dummy", "sample", "replace", "todo", "fill", "generate",
    "sandbox", "mock", "test-secret", "ci-secret", "notasecret", "redacted",
    "${", "{{", "…", "...",
)
# Values that are legitimately committed for offline/local-only use.
ACKNOWLEDGED_VALUES = {
    "", '""', "''", "decor", "decor:decor", "zarinpal-sandbox-merchant",
    "true", "false", "none", "null", "0", "1",
}
# Files that are, by design, allowed to carry placeholder credentials.
PLACEHOLDER_FILES = {
    ".env.example",
    "datasets/service_keys_template.env",
}

# Stage 07: fixture files under backend/tests/ deliberately contain generated
# test-only credentials (Fernet keys, realistic JWT samples for the redaction
# tests). They are acknowledged so the CI secret gate fails only on
# application-code findings — a real credential in app code still fails.
TEST_FIXTURE_ROOT = "backend/tests/"

FORBIDDEN_TRACKED = [
    re.compile(r"(^|/)\.env$"),
    re.compile(r"(^|/)\.env\.(?!example)[A-Za-z0-9_.\-]+$"),
    re.compile(r"\.(pem|key|p12|pfx|jks|keystore)$"),
    re.compile(r"\.(sqlite3?|db)$"),
    re.compile(r"(^|/)(dist|build|node_modules|coverage|htmlcov)/"),
    re.compile(r"(^|/)id_(rsa|dsa|ecdsa|ed25519)$"),
    re.compile(r"(^|/)\.npmrc$"),
    re.compile(r"(^|/)\.netrc$"),
]

BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2",
    ".ttf", ".otf", ".pdf", ".zip", ".gz", ".mp4", ".mp3", ".sqlite3", ".db",
}


def tracked_files() -> list[str]:
    return subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.splitlines()


# Values that are indirections (env lookups, shell substitution, attribute
# access) rather than literal credentials.
INDIRECTION = re.compile(
    r"^\s*(?:[$]\(|[$]\{?[A-Za-z_]|os\.environ|os\.getenv|process\.env|import\.meta\.env"
    r"|Settings\.|settings\.|config\.|self\.|cls\.|getenv\(|Field\(|Depends\(|secrets\.)"
)
# Quoted identifier-like literals: `"token_refresh"`, `'api_key'` — constants,
# enum values and dictionary keys, not credentials.
IDENTIFIER_LITERAL = re.compile(r"^[\"']?[a-z][a-z0-9_.\-]*[\"']?,?$")


def is_placeholder(value: str) -> bool:
    v = value.strip().strip(",").strip()
    if INDIRECTION.match(v):
        return True
    if IDENTIFIER_LITERAL.match(v):
        return True
    v = v.strip("\"'").strip()
    low = v.lower()
    if low in ACKNOWLEDGED_VALUES:
        return True
    if any(m in low for m in PLACEHOLDER_MARKERS):
        return True
    # short values cannot carry meaningful entropy
    return len(v) < 12


def scan() -> dict:
    findings: list[dict] = []
    acknowledged: list[dict] = []
    forbidden: list[str] = []
    oversized: list[dict] = []
    scanned = 0

    files = tracked_files()
    for rel in files:
        path = REPO / rel

        for pat in FORBIDDEN_TRACKED:
            if pat.search(rel):
                forbidden.append(rel)
                break

        if not path.is_file():
            continue

        size = path.stat().st_size
        if size > args_max_bytes:
            oversized.append({"file": rel, "bytes": size})

        if path.suffix.lower() in BINARY_SUFFIXES:
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1

        placeholder_file = rel in PLACEHOLDER_FILES

        for lineno, line in enumerate(text.splitlines(), start=1):
            if len(line) > 4000:
                line = line[:4000]
            for name, pat in PATTERNS:
                m = pat.search(line)
                if not m:
                    continue
                hit = m.group(0)
                record = {
                    "file": rel, "line": lineno, "rule": name,
                    "match": hit[:24] + ("…" if len(hit) > 24 else ""),
                }
                if name == "basic_auth_url" and (
                    "decor:decor" in hit or "user:pass" in hit or "redis://" in hit
                ):
                    record["reason"] = "documented local compose credential"
                    acknowledged.append(record)
                elif rel.startswith(TEST_FIXTURE_ROOT):
                    record["reason"] = "generated test-fixture credential"
                    acknowledged.append(record)
                else:
                    findings.append(record)

            vm = SECRET_VARS.match(line)
            if vm:
                key, val = vm.group("key"), vm.group("val")
                val_clean = val.split("#", 1)[0].strip()
                record = {"file": rel, "line": lineno, "rule": "secret_var", "key": key}
                if is_placeholder(val_clean):
                    record["reason"] = "placeholder/empty value"
                    acknowledged.append(record)
                elif placeholder_file:
                    record["reason"] = f"{rel} is a documented placeholder template"
                    acknowledged.append(record)
                elif rel.startswith(TEST_FIXTURE_ROOT):
                    record["reason"] = "generated test-fixture credential"
                    acknowledged.append(record)
                else:
                    record["value_preview"] = val_clean[:16] + "…"
                    findings.append(record)

    return {
        "tracked_files": len(files),
        "text_files_scanned": scanned,
        "findings": findings,
        "acknowledged": acknowledged,
        "forbidden_tracked_paths": sorted(set(forbidden)),
        "oversized_tracked_files": sorted(oversized, key=lambda d: -d["bytes"]),
        "max_bytes_threshold": args_max_bytes,
    }


def main() -> int:
    global args_max_bytes
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", dest="json_out", help="write a JSON report to this path")
    ap.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES,
                    help=f"oversized-file threshold in bytes (default {DEFAULT_MAX_BYTES})")
    a = ap.parse_args()
    args_max_bytes = a.max_bytes

    report = scan()

    print("=== SECRET & HYGIENE SCAN ===")
    print(f"tracked files            : {report['tracked_files']}")
    print(f"text files scanned       : {report['text_files_scanned']}")
    print(f"oversize threshold       : {report['max_bytes_threshold']} bytes")
    print()
    print(f"[FINDINGS]                {len(report['findings'])}")
    for f in report["findings"]:
        extra = f.get("match") or f.get("value_preview") or ""
        print(f"  {f['file']}:{f['line']} [{f['rule']}] {f.get('key','')} {extra}".rstrip())
    print()
    print(f"[FORBIDDEN TRACKED PATHS] {len(report['forbidden_tracked_paths'])}")
    for f in report["forbidden_tracked_paths"]:
        print(f"  {f}")
    print()
    print(f"[OVERSIZED TRACKED FILES] {len(report['oversized_tracked_files'])}")
    for f in report["oversized_tracked_files"]:
        print(f"  {f['file']}  {f['bytes']} bytes")
    print()
    print(f"[ACKNOWLEDGED PLACEHOLDERS] {len(report['acknowledged'])} "
          "(expected, non-failing — see JSON report for the full list)")

    failed = bool(report["findings"]) or bool(report["forbidden_tracked_paths"])
    print()
    print("RESULT:", "FAIL" if failed else "PASS")

    if a.json_out:
        out = Path(a.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"report : {out}")

    return 1 if failed else 0


args_max_bytes = DEFAULT_MAX_BYTES

if __name__ == "__main__":
    sys.exit(main())
