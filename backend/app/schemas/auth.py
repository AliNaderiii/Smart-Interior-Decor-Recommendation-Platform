from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.sanitize import SafeText

#: V2 (A04): reject unknown fields on every auth payload.
STRICT = ConfigDict(extra="forbid")


class RegisterIn(BaseModel):
    model_config = STRICT

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: SafeText(max_length=200) = ""
    role: str = Field(default="homeowner", pattern="^(homeowner|designer)$")


class LoginIn(BaseModel):
    model_config = STRICT

    email: EmailStr
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
