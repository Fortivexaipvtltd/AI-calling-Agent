from __future__ import annotations

from ..config import settings


def record(db, *, action: str, entity: str = "", entity_id: str = "",
           actor: str = "system", org_id: str | None = None,
           payload: dict | None = None) -> None:
    """Append one immutable event. Never raises into the caller."""
    try:
        from ..models import EventLog
        db.add(EventLog(org_id=org_id or settings.default_org_id, actor=actor,
                        action=action, entity=entity, entity_id=entity_id,
                        payload=payload or {}))
        db.flush()
    except Exception:
        pass


def query(db, *, org_id: str | None = None, entity_id: str = "",
          action: str = "", limit: int = 100) -> list[dict]:
    from sqlalchemy import select

    from ..models import EventLog
    stmt = select(EventLog).where(
        EventLog.org_id == (org_id or settings.default_org_id))
    if entity_id:
        stmt = stmt.where(EventLog.entity_id == entity_id)
    if action:
        stmt = stmt.where(EventLog.action == action)
    stmt = stmt.order_by(EventLog.created_at.desc()).limit(limit)
    return [{"id": e.id, "action": e.action, "entity": e.entity,
             "entity_id": e.entity_id, "actor": e.actor, "payload": e.payload,
             "at": e.created_at.isoformat() if e.created_at else None}
            for e in db.scalars(stmt).all()]
