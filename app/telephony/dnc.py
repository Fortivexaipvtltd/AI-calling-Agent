from __future__ import annotations

from ..config import settings


def normalize(phone: str) -> str:
    return "".join(ch for ch in (phone or "") if ch.isdigit() or ch == "+")


def is_blocked(db, phone: str) -> bool:
    from ..models import DoNotCall
    p = normalize(phone)
    if not p:
        return True
    return db.get(DoNotCall, p) is not None


def add(db, phone: str, reason: str = "opt_out") -> dict:
    from ..models import DoNotCall
    p = normalize(phone)
    if not p:
        return {"ok": False, "error": "empty_phone"}
    if db.get(DoNotCall, p) is None:
        db.add(DoNotCall(phone=p, org_id=settings.default_org_id, reason=reason))
        db.flush()
    return {"ok": True, "phone": p, "reason": reason}


def remove(db, phone: str) -> dict:
    from ..models import DoNotCall
    row = db.get(DoNotCall, normalize(phone))
    if row:
        db.delete(row)
        db.flush()
    return {"ok": True, "phone": normalize(phone)}


def list_all(db) -> list[dict]:
    from sqlalchemy import select

    from ..models import DoNotCall
    return [{"phone": r.phone, "reason": r.reason,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in db.scalars(select(DoNotCall)).all()]
