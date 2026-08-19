"""Application configuration.

All configuration flows through Pydantic Settings loaded from the
environment / ``.env`` file.  No secrets are ever hardcoded — see
``.env.example`` at the repository root for documentation of every var.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
