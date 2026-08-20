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

    # ---- Database ----
    DATABASE_URL: str = "sqlite:///./decor.sqlite3"

    # ---- Redis ----
    REDIS_URL: str = ""  # empty -> fakeredis (dev/test only)
    RECOMMEND_CACHE_TTL: int = 3600
    RECOMMEND_RATE_LIMIT_PER_MINUTE: int = 20  # 0 disables (load tests)

    # ---- AI ----
    AI_PROVIDER: Literal["gemini", "openai", "mock"] = "mock"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
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

    @property
    def is_postgres(self) -> bool:
        return self.DATABASE_URL.startswith(("postgresql", "postgres"))

    #: V2 (OWASP A02): refuse to boot production with a weak/default signing key.
    DEFAULT_SECRET: ClassVar[str] = "dev-only-secret-change-me"

    def validate_runtime(self) -> None:
        """Fail fast on insecure production configuration."""
        if self.APP_ENV != "production":
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
        if problems:
            raise RuntimeError(
                "Insecure production configuration:\n  - " + "\n  - ".join(problems)
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
