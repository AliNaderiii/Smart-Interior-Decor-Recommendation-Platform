"""Shared FastAPI dependencies: current user, role guards, DB session."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.cookies import ACCESS_COOKIE, verify_csrf
from app.core.redis_client import get_redis
from app.core.security import JWTError, decode_token
from app.db.session import get_db
from app.models.user import User

bearer = HTTPBearer(auto_error=False)


#: Unsafe methods must carry the double-submit CSRF token when the caller is
#: authenticating via cookies (Bearer callers are exempt — not CSRF-able).
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the caller from a Bearer header (v1) or an httpOnly cookie (v2)."""
    token = creds.credentials if creds is not None else None
    from_cookie = False
    if token is None and settings.USE_COOKIE_AUTH:
        token = request.cookies.get(ACCESS_COOKIE)
        from_cookie = token is not None
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    # A02/CSRF: cookie-authenticated state changes need the echoed token.
    if from_cookie and request.method in _UNSAFE_METHODS and not verify_csrf(request):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF token missing or invalid")

    try:
        payload = decode_token(token, expected_type="access")
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    if get_redis().get(f"blacklist:{payload['jti']}"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token revoked")
    user = db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


def require_role(*roles: str):
    def guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user

    return guard


require_admin = require_role("admin")
require_designer = require_role("designer", "admin")
