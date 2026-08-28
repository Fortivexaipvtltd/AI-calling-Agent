from __future__ import annotations

from fastapi import Header

from ..config import settings


def current_org(x_org_id: str | None = Header(default=None)) -> str:
    """Resolve the active tenant. In production the org comes from the
    authenticated principal; the X-Org-Id header allows an owner/admin to scope
    a request. Falls back to the default org for local/dev."""
    if x_org_id:
        return x_org_id.strip()
    return settings.default_org_id
