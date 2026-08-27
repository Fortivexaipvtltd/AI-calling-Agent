from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from ..config import settings


@dataclass
class UsageRecord:
    org_id: str
    metric: str            # call_minutes | llm_tokens | sms | whatsapp | tts_chars
    quantity: float
    at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    id: str = field(default_factory=lambda: f"use_{uuid.uuid4().hex[:10]}")


# What each metric costs (INR). Some are configurable via settings.
UNIT_PRICES = {
    "call_minutes": settings.price_per_call_minute_inr,
    "llm_tokens": settings.price_per_llm_1k_tokens_inr / 1000.0,
    "sms": 0.25,
    "whatsapp": 0.35,
    "tts_chars": 0.0003,
}


class BillingService:
    """Meters usage per org and produces invoices. In-memory ledger locally;
    the same records map to a billing provider (Stripe metered) unchanged."""

    def __init__(self) -> None:
        self.records: list[UsageRecord] = []  # in-memory fallback for tests/offline

    def record(self, org_id: str, metric: str, quantity: float) -> UsageRecord:
        rec = UsageRecord(org_id=org_id, metric=metric, quantity=float(quantity))
        self.records.append(rec)
        # Also persist durably so usage survives restarts.
        try:
            from ..db import SessionLocal
            from ..models import UsageRecordRow
            db = SessionLocal()
            try:
                db.add(UsageRecordRow(org_id=org_id, metric=metric, quantity=float(quantity)))
                db.commit()
            finally:
                db.close()
        except Exception:
            pass  # DB not initialised (unit tests) -> memory ledger still works
        return rec

    def usage(self, org_id: str) -> dict:
        totals: dict[str, float] = defaultdict(float)
        # Prefer durable rows; fall back to memory if the table isn't there.
        try:
            from sqlalchemy import select

            from ..db import SessionLocal
            from ..models import UsageRecordRow
            db = SessionLocal()
            try:
                rows = db.scalars(select(UsageRecordRow).where(
                    UsageRecordRow.org_id == org_id)).all()
                if rows:
                    for r in rows:
                        totals[r.metric] += r.quantity
                    return dict(totals)
            finally:
                db.close()
        except Exception:
            pass
        for r in self.records:
            if r.org_id == org_id:
                totals[r.metric] += r.quantity
        return dict(totals)

    def invoice(self, org_id: str) -> dict:
        totals = self.usage(org_id)
        lines = []
        subtotal = 0.0
        for metric, qty in sorted(totals.items()):
            unit = UNIT_PRICES.get(metric, 0.0)
            amount = round(qty * unit, 2)
            subtotal += amount
            lines.append({"metric": metric, "quantity": round(qty, 2),
                          "unit_price_inr": unit, "amount_inr": amount})
        tax = round(subtotal * 0.18, 2)  # GST
        return {"invoice_id": f"inv_{uuid.uuid4().hex[:10]}", "org_id": org_id,
                "currency": "INR", "lines": lines, "subtotal_inr": round(subtotal, 2),
                "tax_inr": tax, "total_inr": round(subtotal + tax, 2),
                "issued_at": datetime.utcnow().isoformat()}


billing = BillingService()
