from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.sanitize import SafeText

#: V2 (A04): reject unknown fields on every auth payload.
STRICT = ConfigDict(extra="forbid")


class RegisterIn(BaseModel):
    model_config = STRICT

    email: EmailStr = Field(max_length=254)
    # Stage 03 (T-10): bcrypt hashes at most the first 72 **bytes** of its
    # input and silently discards the rest. With the previous 128-character
    # bound, "<72 identical bytes>A" and "<72 identical bytes>B" produced the
    # same hash, so a user who believed they had a 100-character passphrase
    # actually had a 72-byte one and any prefix-sharing variant authenticated
    # them. Rejecting at the edge with an explicit message is honest; silently
    # truncating a credential is not. Existing hashes are unaffected — this
    # bounds new registrations only, and `LoginIn` deliberately keeps the wider
    # bound so pre-existing passwords still verify.
    password: str = Field(min_length=12, max_length=72)
    full_name: SafeText(max_length=200) = ""
    role: str = Field(default="homeowner", pattern="^(homeowner|designer)$")

    @field_validator("password")
    @classmethod
    def _password_strength(cls, value: str) -> str:
        """Minimum viable strength policy.

        Deliberately *not* a character-class checklist (NIST SP 800-63B
        explicitly advises against composition rules, which push users toward
        `Password1!`). Length is the control; the two rejections below cover the
        cases length alone does not: byte-length overflow, and the handful of
        strings that appear at the top of every credential-stuffing list.
        """
        if len(value.encode("utf-8")) > 72:
            raise ValueError(
                "password must be at most 72 bytes (bcrypt truncates beyond that)"
            )
        if value.lower() in _BANNED_PASSWORDS:
            raise ValueError("password is among the most commonly breached passwords")
        # NIST SP 800-63B §5.1.1.2 does ask verifiers to reject "repetitive or
        # sequential characters" — that is a *content* check, not a composition
        # rule, so it belongs here. `aaaaaaaaaaaa` and `123456789012` are long
        # enough to pass a length rule while carrying almost no entropy.
        if len(set(value)) <= 4:
            raise ValueError("password repeats too few distinct characters")
        if _is_sequential(value):
            raise ValueError("password is a simple character sequence")
        return value


def _is_sequential(value: str) -> bool:
    """True for runs like `123456789012`, `abcdefghijkl` or their reverses."""
    if len(value) < 4:
        return False
    deltas = {ord(b) - ord(a) for a, b in zip(value, value[1:])}
    return deltas in ({1}, {-1})



#: A deliberately tiny list. A real deployment should front this with a k-anonymity
#: breach lookup (HIBP range API) — recorded as a residual risk, not faked here.
_BANNED_PASSWORDS = frozenset({
    "password", "password1", "password123", "passw0rd", "12345678", "123456789",
    "1234567890", "qwertyuiop", "letmein123", "iloveyou123", "admin123",
    "welcome123", "changeme123", "smartdecor", "smartdecor123",
})


class LoginIn(BaseModel):
    model_config = STRICT

    email: EmailStr = Field(max_length=254)
    # Wider than RegisterIn on purpose: accounts created before the 72-byte
    # bound must still be able to authenticate.
    password: str = Field(max_length=128)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshIn(BaseModel):
    model_config = STRICT

    refresh_token: str = Field(default="", max_length=2048)


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: str
    is_active: bool
    subscription_active: bool = False
    subscription_plan: str = "free"
