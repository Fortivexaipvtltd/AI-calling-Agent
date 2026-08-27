from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request

from ..business.teams import permitted
from ..config import settings
from .keys import Principal, verify

# A permissive principal used when auth is disabled (local dev / tests).
_DEV_PRINCIPAL = Principal(key_id="dev", org_id=settings.default_org_id, role="owner",
                           name="local-dev")


def _extract_token(authorization: str | None, x_api_key: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if x_api_key:
        return x_api_key.strip()
    return ""


async def get_principal(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> Principal:
    """Authenticate the caller. When AUTH_ENABLED=0 this is a no-op that returns a
    dev principal, so local runs and tests need no credentials. In production
    (AUTH_ENABLED=1) a valid bearer token or X-API-Key is required."""
    if not settings.auth_enabled:
        request.state.principal = _DEV_PRINCIPAL
        return _DEV_PRINCIPAL
    token = _extract_token(authorization, x_api_key)
    principal = verify(token)
    if not principal:
        raise HTTPException(status_code=401, detail="invalid_or_missing_api_key")
    request.state.principal = principal
    return principal


def require(permission: str):
    """Route dependency enforcing an RBAC permission, e.g. require('calls:create')."""

    async def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        if settings.rbac_enabled and not permitted(principal.role, permission):
            raise HTTPException(status_code=403,
                                detail=f"forbidden:{principal.role}:{permission}")
        return principal

    return _dep
