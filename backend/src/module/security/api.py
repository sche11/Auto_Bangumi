from datetime import datetime

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from module.conf import settings
from module.database import Database
from module.mcp.security import _is_allowed
from module.models.user import User, UserUpdate

from .jwt import verify_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

active_user: dict[str, datetime] = {}

try:
    from module.__version__ import VERSION
except ImportError:
    VERSION = "DEV_VERSION"

DEV_AUTH_BYPASS = VERSION == "DEV_VERSION"


def check_login_ip(request: Request):
    """Dependency that enforces login IP whitelist.

    If ``settings.security.login_whitelist`` is empty, all IPs are allowed.
    """
    whitelist = settings.security.login_whitelist
    if not whitelist:
        return
    client_host = request.client.host if request.client else None
    if not client_host or not _is_allowed(client_host, whitelist):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="IP not in login whitelist",
        )


async def get_current_user(request: Request, token: str = Cookie(None)):
    """FastAPI dependency that validates the current session.

    Accepts authentication via (in order of precedence):
    1. DEV_AUTH_BYPASS when running as DEV_VERSION.
    2. ``Authorization: Bearer <token>`` header matching ``login_tokens``.
    3. HttpOnly ``token`` cookie containing a valid JWT with an active session.
    """
    if DEV_AUTH_BYPASS:
        return "dev_user"
    # Check bearer token bypass
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        api_token = auth_header[7:]
        if api_token and api_token in settings.security.login_tokens:
            return "api_token_user"
    if not token:
        raise UNAUTHORIZED
    payload = verify_token(token)
    username = payload.get("sub") if payload else None
    if not username or username not in active_user:
        raise UNAUTHORIZED
    return username


async def get_token_data(token: str = Depends(oauth2_scheme)):
    """FastAPI dependency that decodes and returns the OAuth2 bearer token payload."""
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token"
        )
    return payload


def update_user_info(user_data: UserUpdate, current_user):
    """Persist updated credentials for *current_user* to the database."""
    try:
        with Database() as db:
            db.user.update_user(current_user, user_data)
        return True
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def auth_user(user: User):
    """Verify credentials and register the user in ``active_user`` on success."""
    with Database() as db:
        resp = db.user.auth_user(user)
        if resp.status:
            active_user[user.username] = datetime.now()
        return resp


UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
)
