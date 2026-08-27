#!/usr/bin/env python3
"""Prove the installed environment matches requirements.lock.txt (T-1.5).

CI claiming "we install the locked set" is worth nothing without evidence. A
``pip install -r requirements.lock.txt`` can still drift from the lockfile: a
later step can install something that resolves a pin upwards, a
platform-conditional marker can skip a package, or the lockfile can simply be
stale relative to what the image already had.

This script compares the RESOLVED environment (``pip freeze``, i.e. what is
actually importable) against the lockfile, prints a unified diff, and writes a
machine-readable report that CI uploads as a job artifact.

Diff semantics:
  MISSING   in the lockfile but not installed  -> hard failure
  MISMATCH  installed at a different version   -> hard failure
  EXTRA     installed but not in the lockfile  -> reported; only fails with
            --strict-extra, because CI legitimately adds tooling (ruff,
            pip-audit) on top of the application's locked set.

Exit codes:
    0  the locked set is installed exactly (modulo tolerated extras)
    1  drift detected

Usage:
    python scripts/verify_lock_install.py
    python scripts/verify_lock_install.py --json-out lock-verification.json
    python scripts/verify_lock_install.py --ignore-extra ruff --ignore-extra pip-audit
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = BACKEND / "requirements.lock.txt"

#: Packaging tooling that pip itself manages; never part of the app's runtime
#: contract and routinely upgraded by `pip install --upgrade pip`.
DEFAULT_IGNORED_EXTRAS = {"pip", "setuptools", "wheel", "pkg-resources", "distribute"}

PIN = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([^\s;#]+)")


def normalise(name: str) -> str:
    """PEP 503 normalisation — `PyYAML`, `pyyaml` and `py_yaml` are one name."""
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_pins(text: str) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "-")):
            continue
        match = PIN.match(stripped)
        if match:
            pins[normalise(match.group(1))] = match.group(2).strip()
    return pins


def pip_freeze() -> str:
    completed = subprocess.run(
        [sys.executable, "-m", "pip", "freeze", "--all"],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--freeze-out", type=Path, default=None)
    parser.add_argument("--ignore-extra", action="append", default=[])
    parser.add_argument(
        "--strict-extra",
        action="store_true",
        help="also fail when packages outside the lockfile are installed",
    )
    args = parser.parse_args()

    locked = parse_pins(args.lock.read_text(encoding="utf-8"))
    freeze_text = pip_freeze()
    installed = parse_pins(freeze_text)

    if args.freeze_out:
        args.freeze_out.write_text(freeze_text, encoding="utf-8")

    ignored = DEFAULT_IGNORED_EXTRAS | {normalise(n) for n in args.ignore_extra}

    missing = sorted(name for name in locked if name not in installed)
    mismatched = sorted(
        (name, locked[name], installed[name])
        for name in locked
        if name in installed and locked[name] != installed[name]
    )
    extra = sorted(
        name for name in installed if name not in locked and name not in ignored
    )

    print("=" * 72)
    print("Locked-dependency install verification")
    print(f"  lockfile:  {args.lock}")
    print(f"  python:    {sys.version.split()[0]} ({sys.executable})")
    print(f"  timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 72)
    print(f"packages pinned in lockfile: {len(locked)}")
    print(f"packages resolved in env:    {len(installed)}")
    print()

    print("--- requirements.lock.txt (pinned)")
    print("+++ pip freeze (resolved)")
    if not (missing or mismatched or extra):
        print("(no differences)")
    for name in missing:
        print(f"- {name}=={locked[name]}      # MISSING: pinned but not installed")
    for name, want, got in mismatched:
        print(f"- {name}=={want}      # MISMATCH: lockfile")
        print(f"+ {name}=={got}      # MISMATCH: installed")
    for name in extra:
        print(f"+ {name}=={installed[name]}      # EXTRA: installed, not in lockfile")

    print()
    print(f"MISSING:  {len(missing)}")
    print(f"MISMATCH: {len(mismatched)}")
    print(f"EXTRA:    {len(extra)} (tolerated unless --strict-extra)")

    failed = bool(missing or mismatched) or (args.strict_extra and bool(extra))

    if args.json_out:
        args.json_out.write_text(
            json.dumps(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "lockfile": str(args.lock),
                    "python": sys.version,
                    "counts": {
                        "locked": len(locked),
                        "installed": len(installed),
                        "missing": len(missing),
                        "mismatched": len(mismatched),
                        "extra": len(extra),
                    },
                    "missing": {name: locked[name] for name in missing},
                    "mismatched": [
                        {"package": n, "locked": w, "installed": g} for n, w, g in mismatched
                    ],
                    "extra": {name: installed[name] for name in extra},
                    "result": "fail" if failed else "pass",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nreport written to {args.json_out}")

    print()
    if failed:
        print("FAIL: the installed environment does not match the lockfile.")
        return 1
    print("PASS: the installed environment matches requirements.lock.txt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
