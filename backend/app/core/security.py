"""Security primitives: bcrypt password hashing, JWT tokens, Fernet at-rest
encryption abstraction (MVP KMS — documented path to cloud KMS in
docs/ARCHITECTURE.md).

Stage 07 (IR-SEC-002): the JWT library is **PyJWT** (``pyjwt[crypto]``), not
python-jose. python-jose's transitive ``ecdsa`` dependency carried the
unfixed PYSEC-2026-1325 advisory; PyJWT performs the same HS256/384/512
operations on top of ``cryptography`` and removes that code path entirely.
``JWTError`` is re-exported as an alias of PyJWT's base ``InvalidTokenError``
so the two call sites (``app/api/deps.py``, ``app/api/routes/auth.py``) keep
their ``except JWTError`` semantics unchanged.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from cryptography.fernet import Fernet
from jwt.exceptions import InvalidTokenError as JWTError
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# --------------------------------------------------------------------------
# Passwords (bcrypt)
# --------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except ValueError:
        return False


# --------------------------------------------------------------------------
# JWT (access 15 min / refresh 7 days, jti for Redis blacklist)
# --------------------------------------------------------------------------
def create_token(
    subject: str,
    token_type: Literal["access", "refresh"],
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT for ``subject`` (user id).

    Every token carries a unique ``jti`` so refresh tokens can be
    blacklisted in Redis on logout.
    """
    if expires_delta is None:
        expires_delta = (
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
            if token_type == "access"
            else timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        )
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    """Decode and validate a JWT. Raises ``JWTError`` on any problem.

    PyJWT 2.x requires the ``algorithms`` argument (no algorithm confusion —
    it defaults to none) and rejects tokens whose ``alg`` is not in the
    allowlist, which config.py pins to the HMAC family (Stage 03, T-05).
    """
    payload = jwt.decode(
        token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )
    if expected_type and payload.get("type") != expected_type:
        raise JWTError(f"expected {expected_type} token")
    return payload


__all__ = [
    "hash_password",
    "verify_password",
    "create_token",
    "decode_token",
    "JWTError",
    "encrypt_at_rest",
    "decrypt_at_rest",
]


# --------------------------------------------------------------------------
# Encryption at rest (Fernet KMS abstraction)
# --------------------------------------------------------------------------
class KMSClient:
    """MVP KMS abstraction.

    Today the key comes from ``FERNET_KEY`` env var; the interface is
    intentionally identical to what a cloud KMS wrapper (AWS KMS, Arvan
    Vault) would expose, so swapping is a one-file change.
    """

    def __init__(self) -> None:
        key = settings.FERNET_KEY or Fernet.generate_key().decode()
        self._fernet = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode()).decode()


_kms: KMSClient | None = None


def _get_kms() -> KMSClient:
    global _kms
    if _kms is None:
        _kms = KMSClient()
    return _kms


def encrypt_at_rest(plaintext: str) -> str:
    return _get_kms().encrypt(plaintext)


def decrypt_at_rest(ciphertext: str) -> str:
    return _get_kms().decrypt(ciphertext)
