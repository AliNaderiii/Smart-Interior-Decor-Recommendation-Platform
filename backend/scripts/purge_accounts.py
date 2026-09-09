"""Operator CLI: bulk account erasure through ``DELETE /admin/users/{id}``.

Written for the P4-B clean-up of the live demo (35 throwaway ``*@example.com``
accounts left behind by load tests and probes), kept because an operator will
need it again — a batch of GDPR requests, a spam-registration wave, a staging
reset. It deliberately goes through the public API rather than the database:
every deletion is authenticated as a named administrator, guarded by the same
409 rules, audited under the actor, and purges Redis — exactly what a click in
``/admin/users`` does, one account at a time.

Dry-run is the default. Nothing is deleted until you pass ``--yes``.

    # what WOULD be deleted (no changes)
    python scripts/purge_accounts.py --api https://smartdecor-backend.onrender.com/api/v1 \\
        --match "*@example.com"

    # do it, recording a reason on every audit row
    python scripts/purge_accounts.py --api https://smartdecor-backend.onrender.com/api/v1 \\
        --match "*@example.com" --reason "probe accounts (P4-B clean-up)" --yes

The administrator's password is asked interactively (never a flag, never an
environment variable, so it lands in neither shell history nor process lists).
``--token`` accepts an existing access token for automation.

Safety rails:
  * ``--match`` is a glob on the e-mail (``fnmatch``, case-insensitive);
    ``--protect`` globs are never deleted (default ``*@smartdecor.dev``);
  * the acting administrator is always skipped (the API would refuse with
    409 anyway);
  * administrators are skipped unless ``--include-admins`` is given;
  * the plan is printed and, without ``--yes``, that is where it stops.

Exit codes: 0 done (or dry-run), 1 at least one deletion failed, 2 bad usage
or authentication failure.
"""
from __future__ import annotations

import argparse
import fnmatch
import getpass
import sys
from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_PROTECT = ("*@smartdecor.dev",)


@dataclass(frozen=True)
class Plan:
    targets: list[dict[str, Any]]
    skipped: list[tuple[dict[str, Any], str]]


def _matches(email: str, patterns: tuple[str, ...] | list[str]) -> bool:
    low = email.lower()
    return any(fnmatch.fnmatchcase(low, p.lower()) for p in patterns)


def select_targets(
    users: list[dict[str, Any]],
    *,
    match: list[str],
    protect: list[str],
    actor_id: str,
    include_admins: bool = False,
) -> Plan:
    """Pure selection step, unit-tested separately from the HTTP calls."""
    targets: list[dict[str, Any]] = []
    skipped: list[tuple[dict[str, Any], str]] = []
    for u in users:
        email = str(u.get("email", ""))
        if not _matches(email, match):
            continue
        if u.get("id") == actor_id:
            skipped.append((u, "acting administrator"))
        elif _matches(email, protect):
            skipped.append((u, "protected pattern"))
        elif u.get("role") == "admin" and not include_admins:
            skipped.append((u, "administrator (use --include-admins)"))
        else:
            targets.append(u)
    return Plan(targets=targets, skipped=skipped)


def _login(client: httpx.Client, email: str, password: str) -> tuple[str, str]:
    resp = client.post("/auth/login", json={"email": email, "password": password})
    if resp.status_code != 200:
        raise SystemExit(f"login failed: HTTP {resp.status_code} {resp.text[:200]}")
    data = resp.json()["data"]
    return data["access_token"], data["user"]["id"]


def _whoami(client: httpx.Client) -> str:
    resp = client.get("/auth/me")
    if resp.status_code != 200:
        raise SystemExit(f"token rejected: HTTP {resp.status_code} {resp.text[:200]}")
    return resp.json()["data"]["id"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--api", required=True,
                        help="API base, e.g. https://host/api/v1 or http://localhost:8000/api/v1")
    parser.add_argument("--match", action="append", required=True,
                        help="e-mail glob to delete (repeatable), e.g. '*@example.com'")
    parser.add_argument("--protect", action="append", default=None,
                        help=f"e-mail glob never deleted (repeatable); default {DEFAULT_PROTECT}")
    parser.add_argument("--include-admins", action="store_true",
                        help="also delete matching administrator accounts")
    parser.add_argument("--reason", default="", help="recorded on the actor's audit row")
    parser.add_argument("--admin-email", default="admin@smartdecor.dev",
                        help="administrator to authenticate as (password is prompted)")
    parser.add_argument("--token", default=None, help="use an existing access token instead")
    parser.add_argument("--yes", action="store_true", help="actually delete (default: dry-run)")
    parser.add_argument("--timeout", type=float, default=60.0,
                        help="per-request timeout in seconds (Render cold start ≈ 60 s)")
    args = parser.parse_args(argv)

    protect = list(args.protect) if args.protect is not None else list(DEFAULT_PROTECT)
    base = args.api.rstrip("/")

    with httpx.Client(base_url=base, timeout=args.timeout) as client:
        if args.token:
            client.headers["Authorization"] = f"Bearer {args.token}"
            actor_id = _whoami(client)
        else:
            secret = getpass.getpass(f"password for {args.admin_email}: ")
            token, actor_id = _login(client, args.admin_email, secret)
            client.headers["Authorization"] = f"Bearer {token}"

        resp = client.get("/admin/users")
        if resp.status_code != 200:
            print(f"GET /admin/users failed: HTTP {resp.status_code} {resp.text[:200]}")
            return 2
        users = resp.json()["data"]
        plan = select_targets(
            users, match=args.match, protect=protect, actor_id=actor_id,
            include_admins=args.include_admins,
        )

        print(f"{len(users)} account(s) on {base}")
        for u, why in plan.skipped:
            print(f"  skip   {u['email']:<45} {why}")
        for u in plan.targets:
            print(f"  DELETE {u['email']:<45} role={u['role']} created={u['created_at'][:10]}")
        print(f"{len(plan.targets)} to delete, {len(plan.skipped)} skipped, "
              f"{len(users) - len(plan.targets)} will remain")

        if not plan.targets:
            return 0
        if not args.yes:
            print("dry-run: nothing deleted. Re-run with --yes to apply.")
            return 0

        failed = 0
        params = {"reason": args.reason} if args.reason else None
        for u in plan.targets:
            r = client.delete(f"/admin/users/{u['id']}", params=params)
            if r.status_code == 200:
                d = r.json()["data"]
                print(f"  ok     {u['email']:<45} pseudonym={d['audit_pseudonym']} "
                      f"audit_rows={d['audit_rows_pseudonymised']}")
            else:
                failed += 1
                print(f"  FAIL   {u['email']:<45} HTTP {r.status_code} {r.text[:120]}")

        remaining = client.get("/admin/users")
        if remaining.status_code == 200:
            print(f"{len(remaining.json()['data'])} account(s) remain")
        print(f"done: {len(plan.targets) - failed} deleted, {failed} failed")
        return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
