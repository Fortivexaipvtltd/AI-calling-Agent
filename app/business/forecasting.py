from __future__ import annotations

from ..config import settings


def forecast(db, *, org_id: str | None = None, deal_value: float = 50000.0) -> dict:
    """Predict revenue from the current pipeline. Uses each lead's conversion
    propensity (predictive score, falling back to close_probability) times the
    average deal value, plus optimistic/pessimistic bands."""
    from sqlalchemy import select

    from ..models import Lead, LeadScore
    org_id = org_id or settings.default_org_id
    leads = db.scalars(select(Lead).where(
        Lead.org_id == org_id, Lead.suppressed == False)).all()  # noqa: E712
    scores = {s.lead_id: s.propensity for s in db.scalars(select(LeadScore)).all()}

    expected_deals = 0.0
    open_leads = 0
    committed = 0
    for l in leads:
        if l.status == "converted":
            committed += 1
            continue
        if l.status == "lost":
            continue
        open_leads += 1
        expected_deals += scores.get(l.id, l.close_probability or 0.0)

    expected_rev = round((expected_deals + committed) * deal_value, 2)
    # Bands: pessimistic 0.7x of open expectation, optimistic 1.3x (capped by open count).
    open_rev = expected_deals * deal_value
    return {
        "deal_value": deal_value,
        "committed_deals": committed,
        "open_leads": open_leads,
        "expected_conversions": round(expected_deals, 2),
        "expected_revenue": expected_rev,
        "pessimistic_revenue": round((committed * deal_value) + open_rev * 0.7, 2),
        "optimistic_revenue": round((committed * deal_value) + open_rev * 1.3, 2),
    }
