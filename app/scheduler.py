from __future__ import annotations

import threading
from datetime import datetime

from sqlalchemy import select

from .config import settings
from .db import SessionLocal
from .events import bus
from .models import Activity, Followup, Lead
from .providers.telephony import TelephonyProvider
from .tools.registry import ToolRegistry


def run_due(now: datetime | None = None) -> dict:
    """Find every scheduled follow-up whose time has come and execute it
    automatically: email/SMS follow-ups get sent, call follow-ups get re-dialed.
    Suppressed leads are skipped. Idempotent — each follow-up runs once."""
    now = now or datetime.utcnow()
    db = SessionLocal()
    executed: list[dict] = []
    try:
        due = db.scalars(
            select(Followup).where(Followup.status == "scheduled", Followup.due_at <= now)
        ).all()
        tools = ToolRegistry()
        tel = TelephonyProvider()
        for fu in due:
            lead = db.get(Lead, fu.lead_id)
            if not lead or lead.suppressed:
                fu.status = "skipped"
                continue
            if fu.channel in ("email", "sms"):
                tools.store["leads"].setdefault(lead.id, {"id": lead.id})
                res = tools.call(f"message.send_{fu.channel}",
                                 {"lead_id": lead.id, "template": fu.reason})
                db.add(Activity(org_id=lead.org_id, lead_id=lead.id, kind=f"followup_{fu.channel}",
                                body=fu.reason))
                executed.append({"followup_id": fu.id, "channel": fu.channel,
                                 "ok": res.get("ok", False)})
            else:  # call
                dial = tel.dial(lead.phone)
                db.add(Activity(org_id=lead.org_id, lead_id=lead.id, kind="followup_call",
                                body=f"redial:{dial.get('status')}"))
                executed.append({"followup_id": fu.id, "channel": "call",
                                 "status": dial.get("status")})
            fu.status = "done"
            bus.emit("followup.created", {"followup_id": fu.id, "executed": True})
        db.commit()
    finally:
        db.close()
    return {"ran_at": now.isoformat(), "executed": executed, "count": len(executed)}


class Scheduler:
    """Background loop that ticks the follow-up runner on an interval."""

    def __init__(self, interval: int | None = None) -> None:
        self.interval = interval or settings.scheduler_interval_seconds
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                run_due()
            except Exception:
                pass  # never let the scheduler die

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


scheduler = Scheduler()
