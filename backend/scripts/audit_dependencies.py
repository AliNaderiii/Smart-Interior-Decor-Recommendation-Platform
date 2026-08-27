#!/usr/bin/env python3
"""Dependency audit gate with an expiring allowlist (Stage 1, T-1.5).

Runs ``pip-audit`` over the **locked** dependency set and reconciles the
findings against ``security/pip-audit-allowlist.yml``.

Why this exists rather than a bare ``pip-audit -r requirements.txt``:

* ``requirements.txt`` holds RANGES (``fastapi>=0.115``). Auditing it audits
  whatever resolves today, which is not what CI installs and not what ships —
  a vulnerable pinned version could sail through while the range looks clean.
  This audits ``requirements.lock.txt``, the set actually installed.
* A finding that cannot be fixed immediately needs an accountable exception,
  not a commented-out job. The allowlist entries carry an owner, a reason and
  a MANDATORY expiry date; an expired entry fails the build.

Exit codes:
    0  no findings, or every finding is covered by a valid allowlist entry
    1  unsuppressed finding(s), an expired/invalid allowlist entry, or a
       stale entry (with ``--strict-stale``)
    2  the audit could not be run at all (pip-audit missing, network failure)

Usage:
    python scripts/audit_dependencies.py
    python scripts/audit_dependencies.py --requirements requirements.lock.txt
    python scripts/audit_dependencies.py --strict-stale
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - CI installs pyyaml
    print("ERROR: pyyaml is required (pip install pyyaml)", file=sys.stderr)
    raise SystemExit(2) from None

BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_REQUIREMENTS = BACKEND / "requirements.lock.txt"
DEFAULT_ALLOWLIST = BACKEND / "security" / "pip-audit-allowlist.yml"

#: An acceptance nobody has revisited in six months is not an accepted risk.
MAX_ACCEPTANCE_DAYS = 180

REQUIRED_FIELDS = ("id", "package", "reason", "owner", "expires")


class AllowlistError(Exception):
    """The allowlist file itself is invalid (bad schema, expired entry)."""


def load_allowlist(path: Path, today: date) -> dict[tuple[str, str], dict[str, Any]]:
    """Parse and VALIDATE the allowlist.

    Raises ``AllowlistError`` on any schema or expiry violation, so a
    malformed or stale acceptance can never silently widen the gate.
    """
    if not path.exists():
        return {}

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("allowlist") or []
    if not isinstance(entries, list):
        raise AllowlistError(f"{path.name}: 'allowlist' must be a list")

    problems: list[str] = []
    parsed: dict[tuple[str, str], dict[str, Any]] = {}

    for index, entry in enumerate(entries):
        where = f"{path.name}[{index}]"
        if not isinstance(entry, dict):
            problems.append(f"{where}: entry must be a mapping")
            continue

        missing = [f for f in REQUIRED_FIELDS if not str(entry.get(f, "")).strip()]
        if missing:
            problems.append(f"{where}: missing required field(s): {', '.join(missing)}")
            continue

        expires_raw = entry["expires"]
        expires = expires_raw if isinstance(expires_raw, date) else None
        if expires is None:
            try:
                expires = datetime.strptime(str(expires_raw), "%Y-%m-%d").date()
            except ValueError:
                problems.append(f"{where}: 'expires' must be YYYY-MM-DD, got {expires_raw!r}")
                continue

        if expires < today:
            problems.append(
                f"{where}: acceptance of {entry['id']} ({entry['package']}) EXPIRED on "
                f"{expires} — fix the dependency or re-justify with a new expiry"
            )
            continue

        horizon = today + timedelta(days=MAX_ACCEPTANCE_DAYS)
        if expires > horizon:
            problems.append(
                f"{where}: 'expires' {expires} is more than {MAX_ACCEPTANCE_DAYS} days out "
                f"(max {horizon}) — acceptances must be revisited"
            )
            continue

        key = (str(entry["id"]).strip().upper(), str(entry["package"]).strip().lower())
        parsed[key] = {**entry, "expires": expires}

    if problems:
        raise AllowlistError("\n".join(problems))

    return parsed


def run_pip_audit(requirements: Path) -> list[dict[str, Any]]:
    """Run pip-audit and return a flat list of findings."""
    command = [
        sys.executable, "-m", "pip_audit",
        "--requirement", str(requirements),
        "--format", "json",
        "--progress-spinner", "off",
    ]
    print(f"$ {' '.join(command)}", flush=True)
    completed = subprocess.run(command, capture_output=True, text=True)

    if not completed.stdout.strip():
        print(completed.stderr, file=sys.stderr)
        raise SystemExit(2)

    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError:
        print(completed.stdout, file=sys.stderr)
        print(completed.stderr, file=sys.stderr)
        raise SystemExit(2) from None

    findings: list[dict[str, Any]] = []
    for dependency in report.get("dependencies", []):
        name = dependency.get("name", "")
        version = dependency.get("version", "")
        for vuln in dependency.get("vulns", []) or []:
            findings.append(
                {
                    "package": name,
                    "version": version,
                    "id": vuln.get("id", ""),
                    "fix_versions": vuln.get("fix_versions", []),
                    "description": (vuln.get("description") or "").strip().splitlines()[:1],
                }
            )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS)
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    parser.add_argument(
        "--strict-stale",
        action="store_true",
        help="fail when an allowlist entry no longer matches any finding",
    )
    args = parser.parse_args()

    today = date.today()
    print(f"Dependency audit — {today.isoformat()}")
    print(f"  requirements: {args.requirements}")
    print(f"  allowlist:    {args.allowlist}")
    print()

    try:
        allowlist = load_allowlist(args.allowlist, today)
    except AllowlistError as exc:
        print("ALLOWLIST INVALID:", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Allowlist entries (valid, unexpired): {len(allowlist)}")
    for (advisory, package), entry in sorted(allowlist.items()):
        remaining = (entry["expires"] - today).days
        print(f"  - {advisory} / {package}: expires {entry['expires']} ({remaining}d) "
              f"— owner {entry['owner']}")
    print()

    findings = run_pip_audit(args.requirements)
    print(f"pip-audit findings: {len(findings)}")

    unsuppressed: list[dict[str, Any]] = []
    matched: set[tuple[str, str]] = set()

    for finding in findings:
        key = (finding["id"].strip().upper(), finding["package"].strip().lower())
        if key in allowlist:
            matched.add(key)
            entry = allowlist[key]
            print(f"  ACCEPTED  {finding['id']}  {finding['package']}=={finding['version']} "
                  f"(expires {entry['expires']}, owner {entry['owner']})")
        else:
            unsuppressed.append(finding)
            fixes = ", ".join(finding["fix_versions"]) or "none published"
            print(f"  VULNERABLE {finding['id']}  {finding['package']}=={finding['version']} "
                  f"-> fix in: {fixes}")

    stale = sorted(set(allowlist) - matched)
    if stale:
        print()
        print("STALE allowlist entries (no matching finding — remove them):")
        for advisory, package in stale:
            print(f"  - {advisory} / {package}")

    print()
    if unsuppressed:
        print(f"FAIL: {len(unsuppressed)} unsuppressed vulnerability(ies).")
        print("Fix by raising the pin in requirements.lock.txt (preferred), or add an")
        print("expiring, justified entry to security/pip-audit-allowlist.yml.")
        return 1

    if stale and args.strict_stale:
        print(f"FAIL: {len(stale)} stale allowlist entry(ies) under --strict-stale.")
        return 1

    print("PASS: no unsuppressed vulnerabilities in the locked dependency set.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
