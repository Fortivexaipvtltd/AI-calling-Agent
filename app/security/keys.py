from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from ..config import settings
from ..db import SessionLocal
from ..models import ApiKey


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _env_hashes() -> set[str]:
    hashes = {h.strip() for h in settings.api_key_hashes.split(",") if h.strip()}
    # Convenience for dev: allow raw keys via API_KEYS, hashed on load.
    hashes |= {hash_key(k.strip()) for k in settings.api_keys.split(",") if k.strip()}
    return hashes


@dataclass
class Principal:
    key_id: str
    org_id: str
    role: str
    name: str = ""


def create_key(org_id: str, name: str = "", role: str = "admin") -> tuple[str, ApiKey]:
    """Mint a new key. Returns (raw_key_shown_once, row). Raw is never stored."""
    raw = "hh_" + secrets.token_urlsafe(32)
    row = ApiKey(org_id=org_id, name=name, role=role, prefix=raw[:8],
                 key_hash=hash_key(raw))
    db = SessionLocal()
    try:
        db.add(row)
        db.commit()
        db.refresh(row)
    finally:
        db.close()
    return raw, row


def verify(raw: str) -> Principal | None:
    """Constant-time verification against env hashes and the DB."""
    if not raw:
        return None
    digest = hash_key(raw)

    # 1) env-provided keys (bootstrap / stateless deployments)
    for h in _env_hashes():
        if hmac.compare_digest(h, digest):
            return Principal(key_id="env", org_id=settings.default_org_id, role="owner")

    # 2) database-backed keys
    db = SessionLocal()
    try:
        row = db.scalar(select(ApiKey).where(ApiKey.key_hash == digest,
                                             ApiKey.active.is_(True)))
        if row:
            row.last_used_at = datetime.utcnow()
            db.commit()
            return Principal(key_id=row.id, org_id=row.org_id, role=row.role, name=row.name)
    finally:
        db.close()
    return None
