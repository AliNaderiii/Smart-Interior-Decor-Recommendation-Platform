"""Development-only demo accounts — the fail-safe gate (Stage 03, IR-001).

Why this module exists
----------------------
Both seeding entrypoints used to contain their own copy of::

    defaults = [("admin@smartdecor.dev", "Admin123!", "admin", ...), ...]
    for email, password, role, name in defaults:
        if not db.scalar(select(User).where(User.email == email)):
            db.add(User(...))

with **no environment guard at all**, and ``docker-compose.yml`` runs one of
those scripts on every backend container start. The credentials are published
in `README.md`, `docs/WALKTHROUGH*.md` and (previously) on the SPA login page,
so a production deployment shipped with a known-password administrator.
Baseline proof: `docs/agent-reports/security-hardening-evidence/03-BEFORE-demo-seeding-probe.txt`.

Design
------
One gate, three independent locks, all of which must be open:

1. ``APP_ENV != "production"`` — **not overridable**. Even
   ``SEED_DEMO_ACCOUNTS=true`` is refused in production; the setting itself is
   rejected at boot by :meth:`Settings.validate_runtime`, so a production
   process that asks for demo accounts does not start at all.
2. ``SEED_DEMO_ACCOUNTS=true`` — explicit opt-in, default ``False`` everywhere.
   Nothing is created by accident, in any environment.
3. The caller must go through :func:`ensure_demo_accounts`; the credential list
   lives here and nowhere else, so there is exactly one place to audit.

Local development convenience is preserved: ``SEED_DEMO_ACCOUNTS=true`` in
``.env`` (or ``make seed-demo``) reproduces the historical behaviour exactly,
including the same three well-known logins. See
`docs/security/DEMO_ACCOUNTS.md`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DemoAccount:
    email: str
    password: str
    role: str
    full_name: str


#: The historical development logins. Documented, low-value, and creatable only
#: under the gate below. Never a secret — treating them as one would be theatre;
#: the control is that they cannot exist in production.
DEMO_ACCOUNTS: tuple[DemoAccount, ...] = (
    DemoAccount("admin@smartdecor.dev", "Admin123!", "admin", "Platform Admin"),
    DemoAccount("designer@smartdecor.dev", "Design123!", "designer", "Sara Designer"),
    DemoAccount("demo@smartdecor.dev", "Demo1234!", "homeowner", "Demo Homeowner"),
)

DEMO_EMAILS: frozenset[str] = frozenset(a.email for a in DEMO_ACCOUNTS)


class DemoSeedRefused(RuntimeError):
    """Raised when demo seeding is explicitly requested but must not happen."""


def demo_seeding_allowed(*, strict: bool = False) -> bool:
    """Return True only when demo accounts may be created.

    ``strict=True`` raises :class:`DemoSeedRefused` instead of returning False
    for the *production* case, so an operator who typed
    ``APP_ENV=production ... --seed-demo-accounts`` gets a hard error rather
    than a silent no-op they might mistake for success.
    """
    if settings.is_production:
        message = (
            "Refusing to create demo/default accounts: APP_ENV=production. "
            "This is not overridable — see docs/security/DEMO_ACCOUNTS.md."
        )
        logger.critical(message)
        if strict:
            raise DemoSeedRefused(message)
        return False
    if not settings.SEED_DEMO_ACCOUNTS:
        logger.info(
            "Skipping demo accounts: SEED_DEMO_ACCOUNTS is false (default). "
            "Set SEED_DEMO_ACCOUNTS=true in a development environment to "
            "create the documented demo logins."
        )
        return False
    return True


def _password_for(account: DemoAccount) -> str:
    override = settings.DEMO_ACCOUNT_PASSWORD or ""
    # BUG-401 hardening: some env-file loaders (notably Docker Compose's
    # `env_file`) do NOT strip inline `#` comments from values, so a template
    # line like `DEMO_ACCOUNT_PASSWORD=  # comment` reaches us with the comment
    # text as the literal password. Treat a value whose stripped form begins
    # with `#` as unset and fall back to the documented dev default — loudly,
    # so a poisoned deployment is visible instead of silently seeding accounts
    # with a comment string as the password.
    if override.strip().startswith("#"):
        logger.warning(
            "Ignoring DEMO_ACCOUNT_PASSWORD: its value starts with '#' and "
            "looks like an inline comment folded in by an env-file loader "
            "(BUG-401), not a real password. Falling back to the documented "
            "development default for %s.",
            account.email,
        )
        return account.password
    return override or account.password


def ensure_demo_accounts(db: Session, *, strict: bool = False) -> list[str]:
    """Create the demo accounts when — and only when — the gate is open.

    Returns the list of emails actually created (empty when refused or when
    they already exist). Never commits: the caller owns the transaction.
    """
    if not demo_seeding_allowed(strict=strict):
        return []

    # Imported lazily so that a module-level import of this file never drags the
    # password hasher (and therefore bcrypt) into a process that will not seed.
    from app.core.security import hash_password
    from app.models.subscription import Subscription
    from app.models.user import User

    created: list[str] = []
    for account in DEMO_ACCOUNTS:
        if db.scalar(select(User).where(User.email == account.email)):
            continue
        user = User(
            email=account.email,
            hashed_password=hash_password(_password_for(account)),
            role=account.role,
            full_name=account.full_name,
        )
        user.subscription = Subscription(plan="free", is_active=False)
        db.add(user)
        created.append(account.email)

    if created:
        logger.warning(
            "DEVELOPMENT ONLY: created %d demo account(s) with well-known "
            "passwords (%s). APP_ENV=%s. These can never be created in "
            "production.",
            len(created), ", ".join(created), settings.APP_ENV,
        )
    return created


def enable_for_this_process(*, reason: str = "explicit CLI flag") -> None:
    """Turn the opt-in on for this process only (``--seed-demo-accounts``).

    Still refused in production: the flag flips the *opt-in*, never the
    environment lock. Raises :class:`DemoSeedRefused` under production so a
    CI/deploy script cannot mistake a no-op for success.
    """
    if settings.is_production:
        raise DemoSeedRefused(
            "--seed-demo-accounts refused: APP_ENV=production. Demo accounts "
            "are never creatable in production (docs/security/DEMO_ACCOUNTS.md)."
        )
    object.__setattr__(settings, "SEED_DEMO_ACCOUNTS", True)
    logger.warning("Demo-account seeding enabled for this process (%s)", reason)


def find_demo_accounts(db: Session) -> list[str]:
    """Return demo emails present in this database (boot-time guard input)."""
    from app.models.user import User

    return list(
        db.scalars(select(User.email).where(User.email.in_(sorted(DEMO_EMAILS)))).all()
    )


def assert_no_demo_accounts_in_production(db: Session) -> None:
    """Refuse to serve production from a database containing demo logins.

    Covers the cases the seeding gate cannot: a dump restored from staging, a
    deployment made before this fix, or a manual insert. Fail-safe by choice —
    a platform that will not start is recoverable in minutes; a platform
    serving traffic with a published admin password is not.
    """
    if not settings.is_production or not settings.REFUSE_DEMO_ACCOUNTS_IN_PRODUCTION:
        return
    try:
        found = find_demo_accounts(db)
    except Exception as exc:  # database not reachable/migrated yet
        logger.warning("Demo-account boot guard could not query users: %s", exc)
        return
    if found:
        raise RuntimeError(
            "Refusing to start: production database contains predictable demo "
            f"account(s): {', '.join(sorted(found))}. Delete or rename them "
            "(and rotate anything they touched) before serving traffic. "
            "See docs/security/DEMO_ACCOUNTS.md."
        )
