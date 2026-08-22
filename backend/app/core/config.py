"""Application configuration.

All configuration flows through Pydantic Settings loaded from the
environment / ``.env`` file.  No secrets are ever hardcoded — see
``.env.example`` at the repository root for documentation of every var.
"""
from __future__ import annotations

from functools import lru_cache
from typing import ClassVar, Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---- App ----
    APP_ENV: Literal["development", "production", "test"] = "development"
    APP_NAME: str = "Smart Decor"
    API_V1_PREFIX: str = "/api/v1"
    FRONTEND_ORIGIN: str = "http://localhost:5173"

    # ---- Security ----
    SECRET_KEY: str = "dev-only-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    FERNET_KEY: str = ""

    # ---- Demo / seed accounts (Stage 03 — IR-001, blocker B-1) ----
    #: Opt-in, default OFF, and **ignored in production**. Historically both
    #: seed entrypoints created `admin@smartdecor.dev / Admin123!` on every run,
    #: and `docker-compose.yml` runs one of them on every backend start — so a
    #: production deployment shipped with a publicly documented admin password.
    #: The gate now lives in `app.core.demo_seed`; this flag only enables it for
    #: development and test. Setting it in production is a boot-time failure,
    #: not a silently ignored value, so a mistake is loud instead of dangerous.
    SEED_DEMO_ACCOUNTS: bool = False
    #: Optional override for the well-known development passwords. Empty means
    #: "use the documented dev defaults" — which are only ever reachable when
    #: SEED_DEMO_ACCOUNTS is true and APP_ENV is not production.
    DEMO_ACCOUNT_PASSWORD: str = ""
    #: Belt and braces: refuse to serve production if a demo account somehow
    #: exists in the database (restored dump, pre-fix deployment, manual seed).
    REFUSE_DEMO_ACCOUNTS_IN_PRODUCTION: bool = True

    # ---- Cookie auth (V2 — OWASP A02) ----
    #: When true, /auth/* also sets HttpOnly access+refresh cookies and the
    #: API accepts them. Body tokens are retained for Bearer/CLI clients.
    USE_COOKIE_AUTH: bool = True
    COOKIE_SECURE: bool = True
    COOKIE_SAMESITE: Literal["strict", "lax", "none"] = "strict"

    # ---- Auth rate limits (V2 — OWASP A07) ----
    #: Coarse per-IP flood guard. Deliberately generous: many legitimate users
    #: share one NAT egress IP, and a strict 5/min here would let one attacker
    #: lock out every colleague behind the same address (turning the control
    #: into a DoS). Targeted guessing is stopped precisely by
    #: `app.core.brute_force` (5 failures per ip+email -> 15 min lockout).
    LOGIN_RATE_LIMIT_PER_MINUTE: int = 30
    REGISTER_RATE_LIMIT_PER_MINUTE: int = 3
    RECOMMEND_IP_RATE_LIMIT_PER_MINUTE: int = 100
    #: Stage 03: the Master Prompt requires abuse controls on login, register,
    #: recommend, **share** and **upload**. The last two had none.
    SHARE_RATE_LIMIT_PER_MINUTE: int = 30
    UPLOAD_RATE_LIMIT_PER_MINUTE: int = 10
    EXPORT_RATE_LIMIT_PER_HOUR: int = 5

    # ---- Database ----
    DATABASE_URL: str = "sqlite:///./decor.sqlite3"

    # ---- Redis ----
    REDIS_URL: str = ""  # empty -> fakeredis (dev/test only)
    RECOMMEND_CACHE_TTL: int = 3600

    # pgvector HNSW search breadth (V2 Phase 2). The pgvector default of 40 is
    # tuned for unfiltered nearest-neighbour search. Our Stage A/B query is a
    # *post-filtered* ANN search (category + budget + is_verified applied on
    # top of the index scan), so the index must walk far more than 40 nodes to
    # still yield CANDIDATE_LIMIT survivors. Measured on a 20.7k-row catalog:
    # ef_search=40 returned 14/100 candidates, 200 -> 58/100, 400 -> 100/100.
    # 400 costs ~9 ms vs ~7 ms and remains faster than the 14 ms exact scan.
    HNSW_EF_SEARCH: int = 400
    RECOMMEND_RATE_LIMIT_PER_MINUTE: int = 20  # 0 disables (load tests)

    # ---- AI ----
    AI_PROVIDER: Literal["gemini", "openai", "mock"] = "mock"
    GEMINI_API_KEY: str = ""
    # Stage 04 remediation (IR-AI-004): gemini-2.0-flash was shut down by
    # Google on 2026-06-01 and gemini-2.5-flash is scheduled for shutdown on
    # 2026-10-16; Google's 2.0-flash migration guidance points at the 3.5
    # Flash generation. The default is therefore gemini-3.5-flash. NOT yet
    # validated with a real API request in this environment (no credentials —
    # the real benchmark stays BLOCKED); see docs/ai/model-versions.md.
    GEMINI_MODEL: str = "gemini-3.5-flash"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    EMBEDDING_BACKEND: Literal["clip", "hash"] = "hash"
    EMBEDDING_DIM: int = 512

    # ---- Storage ----
    STORAGE_BACKEND: Literal["s3", "local"] = "local"
    S3_ENDPOINT: str = ""
    S3_BUCKET: str = ""
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_REGION: str = ""
    S3_PUBLIC_BASE_URL: str = ""
    LOCAL_STORAGE_DIR: str = "./local_storage"
    #: Upload hardening (Stage 03 — OWASP A04/A05). Bytes, pixels and edge
    #: length are all bounded: a 40 KB PNG can still decode to 30 000 x 30 000
    #: pixels and exhaust memory (decompression bomb), so a byte cap alone is
    #: not a limit.
    MAX_UPLOAD_BYTES: int = 8 * 1024 * 1024
    MAX_UPLOAD_PIXELS: int = 40_000_000
    MAX_UPLOAD_EDGE_PX: int = 12_000

    # ---- Payment ----
    PAYMENT_PROVIDER: Literal["zarinpal", "zarinpal_sandbox", "zibal", "mock"] = (
        "zarinpal_sandbox"
    )
    ZARINPAL_MERCHANT_ID: str = "zarinpal-sandbox-merchant"
    PAYMENT_CALLBACK_URL: str = "http://localhost:5173/payment/callback"

    # ---- Email ----
    EMAIL_PROVIDER: Literal["mock", "resend"] = "mock"
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "noreply@smartdecor.dev"

    # ---- Observability (Stage 07) ----
    #: Root log level. Accepts any logging level name (DEBUG..CRITICAL).
    LOG_LEVEL: str = "INFO"
    #: "text" = readable multi-line logs (dev/test default); "json" = one
    #: machine-parseable JSON object per line, redacted, with request_id
    #: correlation (see app/core/observability.py). The production compose
    #: overlay sets LOG_FORMAT=json; the application itself defaults to text.
    LOG_FORMAT: Literal["text", "json"] = "text"
    #: Expose the Prometheus-text /metrics endpoint. Disable only if the
    #: collector is on a hostile network and the proxy cannot restrict it.
    METRICS_ENABLED: bool = True

    @property
    def is_postgres(self) -> bool:
        return self.DATABASE_URL.startswith(("postgresql", "postgres"))

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    #: V2 (OWASP A02): refuse to boot production with a weak/default signing key.
    DEFAULT_SECRET: ClassVar[str] = "dev-only-secret-change-me"

    #: Stage 03 (T-05): the project signs with HMAC. Allowing an asymmetric or
    #: `none` algorithm to be configured would open algorithm-confusion and
    #: would also make the vulnerable `ecdsa` code path (PYSEC-2026-1325)
    #: reachable. Pin the choice to HMAC family members only.
    ALLOWED_JWT_ALGORITHMS: ClassVar[frozenset[str]] = frozenset(
        {"HS256", "HS384", "HS512"}
    )

    #: Stage 03 (T-01): predictable identities that must never exist in a
    #: production database. Kept here (not in the seed scripts) so the API
    #: process can enforce it at boot even if the seeder is never run.
    DEMO_ACCOUNT_EMAILS: ClassVar[tuple[str, ...]] = (
        "admin@smartdecor.dev",
        "designer@smartdecor.dev",
        "demo@smartdecor.dev",
    )

    #: Stage 04 remediation (IR-AI-004): Gemini model IDs that Google has
    #: already shut down. Configuring one is a guaranteed 404 on the first
    #: real request, so validate_runtime refuses them in every environment.
    RETIRED_GEMINI_MODELS: ClassVar[frozenset[str]] = frozenset({
        "gemini-2.0-flash",
        "gemini-2.0-flash-001",
        "gemini-2.0-flash-exp",
        "gemini-2.0-flash-lite",
        "gemini-2.0-flash-lite-001",
    })

    def ai_provider_problems(self) -> list[str]:
        """This instance's provider problems, via the shared authoritative rule."""
        return ai_provider_problems(
            self.AI_PROVIDER,
            has_gemini_key=bool(self.GEMINI_API_KEY),
            has_openai_key=bool(self.OPENAI_API_KEY),
            production=self.is_production,
        )

    def validate_runtime(self) -> None:
        """Fail fast on insecure configuration.

        Checks that apply to *every* environment run first (a broken JWT
        algorithm is not safer in development), then the production-only
        fail-safes. Raises ``RuntimeError`` listing every problem at once —
        an operator fixing a misconfiguration should not have to discover the
        issues one restart at a time.
        """
        universal: list[str] = []
        if self.JWT_ALGORITHM not in self.ALLOWED_JWT_ALGORITHMS:
            universal.append(
                f"JWT_ALGORITHM must be one of "
                f"{sorted(self.ALLOWED_JWT_ALGORITHMS)} (got {self.JWT_ALGORITHM!r})"
            )
        # Applies in every environment and regardless of the active provider:
        # the moment AI_PROVIDER flips to gemini, a retired model id means
        # every real request 404s. Fail fast at boot instead.
        if self.GEMINI_MODEL in self.RETIRED_GEMINI_MODELS:
            universal.append(
                f"GEMINI_MODEL={self.GEMINI_MODEL!r} was shut down by Google "
                f"(see ai.google.dev/gemini-api/docs/deprecations) — every real "
                f"request would fail; set GEMINI_MODEL to a current model "
                f"(default: gemini-3.5-flash)"
            )
        if universal:
            raise RuntimeError(
                "Insecure configuration:\n  - " + "\n  - ".join(universal)
            )

        if not self.is_production:
            return

        problems: list[str] = []
        if self.SECRET_KEY == self.DEFAULT_SECRET:
            problems.append("SECRET_KEY is still the default value")
        if len(self.SECRET_KEY) < 32:
            problems.append(
                f"SECRET_KEY must be >=32 chars (got {len(self.SECRET_KEY)})"
            )
        if not self.REDIS_URL:
            problems.append(
                "REDIS_URL is empty — fakeredis is per-process, so rate limits "
                "and brute-force lockouts would not be shared across workers"
            )
        if self.USE_COOKIE_AUTH and not self.COOKIE_SECURE:
            problems.append("COOKIE_SECURE must be true in production")

        # ---- Stage 03 additions -------------------------------------------
        # T-01: the single most important production invariant of this stage.
        if self.SEED_DEMO_ACCOUNTS:
            problems.append(
                "SEED_DEMO_ACCOUNTS is true — demo/default accounts must never "
                "be created in production (see docs/security/DEMO_ACCOUNTS.md)"
            )
        # T-40: an https SPA cannot be served from an http origin, and a
        # non-https FRONTEND_ORIGIN would end up in the CORS allowlist.
        if not self.FRONTEND_ORIGIN.startswith("https://"):
            problems.append(
                f"FRONTEND_ORIGIN must be an https:// origin in production "
                f"(got {self.FRONTEND_ORIGIN!r})"
            )
        if self.COOKIE_SAMESITE == "none" and not self.COOKIE_SECURE:
            problems.append("COOKIE_SAMESITE=none requires COOKIE_SECURE=true")
        # T-45: an unset Fernet key means a *new* key per worker process, so
        # anything encrypted at rest becomes undecryptable after a restart.
        if not self.FERNET_KEY:
            problems.append(
                "FERNET_KEY is empty — a random key would be generated per "
                "process, making at-rest ciphertext unrecoverable"
            )
        else:
            try:
                from cryptography.fernet import Fernet

                Fernet(self.FERNET_KEY.encode())
            except Exception:
                problems.append(
                    "FERNET_KEY is not a valid urlsafe-base64 32-byte Fernet key"
                )
        if self.STORAGE_BACKEND == "local":
            problems.append(
                "STORAGE_BACKEND=local serves uploaded bytes from the "
                "application origin; production must use S3-compatible storage"
            )
        # Stage 04 remediation: strict provider/key matching (was: any key for
        # any provider, and mock silently allowed in production).
        problems.extend(self.ai_provider_problems())

        if problems:
            raise RuntimeError(
                "Insecure production configuration:\n  - " + "\n  - ".join(problems)
            )


#: Authoritative AI-provider → API-key-field mapping. A key for a different
#: provider must never satisfy validation for the selected one (Stage 04
#: remediation: the old rule accepted *any* key for *any* provider, so
#: ``AI_PROVIDER=gemini`` + only ``OPENAI_API_KEY`` looked configured).
AI_PROVIDER_KEY_FIELDS: dict[str, str] = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def ai_provider_problems(
    provider: str,
    *,
    has_gemini_key: bool,
    has_openai_key: bool,
    production: bool,
) -> list[str]:
    """Single authoritative provider-selection rule (Stage 04 remediation).

    Used by :meth:`Settings.validate_runtime` (startup) **and** by
    ``ai.feature_extractor.FeatureExtractor`` (request-time construction), so
    the two can never drift apart again. Messages are actionable and name the
    exact setting to fix; they never include key values.

    Rules:

    * ``AI_PROVIDER=mock`` is dev/test-only — production must not run on
      keyword-derived features.
    * ``AI_PROVIDER=gemini`` requires ``GEMINI_API_KEY``; ``openai`` requires
      ``OPENAI_API_KEY``. A key for another provider is not accepted.
    * Unknown provider names are rejected.
    """
    problems: list[str] = []
    if provider == "mock":
        if production:
            problems.append(
                "AI_PROVIDER=mock derives features from the image "
                "URL/filename, not from pixels — production must set "
                "AI_PROVIDER=gemini (with GEMINI_API_KEY) or AI_PROVIDER=openai "
                "(with OPENAI_API_KEY); AI_PROVIDER=mock is allowed in "
                "development/test only"
            )
        return problems
    key_field = AI_PROVIDER_KEY_FIELDS.get(provider)
    if key_field is None:
        problems.append(
            f"AI_PROVIDER={provider!r} is not one of "
            f"{sorted(AI_PROVIDER_KEY_FIELDS)} or 'mock'"
        )
        return problems
    has_key = {
        "GEMINI_API_KEY": has_gemini_key,
        "OPENAI_API_KEY": has_openai_key,
    }[key_field]
    if not has_key:
        problems.append(
            f"AI_PROVIDER={provider} requires {key_field} to be set — an API key "
            f"for a different provider is not accepted; set {key_field} or use "
            "AI_PROVIDER=mock in development/test only"
        )
    return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
