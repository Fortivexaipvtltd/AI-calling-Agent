from __future__ import annotations

from ..config import settings

# Transparent, explainable propensity model (logistic blend of signals). No
# external ML dependency; weights are interpretable and tunable. Produces a
# 0..1 conversion probability, an A–D grade, and human-readable reasons so a rep
# understands *why* a lead is hot.

_WEIGHTS = {
    "base": -0.4,
    "engaged_status": 1.4,      # interested/qualified
    "converted_status": 3.0,
    "has_email": 0.3,
    "source_quality": 0.0,      # set per source below
    "attempts_penalty": -0.25,  # per attempt beyond the first
    "recent_positive": 1.1,     # last call sentiment positive
    "objection_penalty": -0.5,
    "explicit_intent": 1.6,     # said enroll/buy/pay
}

_SOURCE_QUALITY = {
    "web-form": 0.8, "landing": 0.7, "referral": 1.0, "ads": 0.4,
    "console": 0.3, "csv": 0.2, "web": 0.6, "unknown": 0.0,
}

_POSITIVE = ("interested", "enroll", "enrol", "buy", "pay", "join", "yes")


def _sigmoid(x: float) -> float:
    import math
    return 1.0 / (1.0 + math.exp(-x))


def score_lead(lead, *, insights: list | None = None) -> dict:
    reasons: list[str] = []
    z = _WEIGHTS["base"]

    status = getattr(lead, "status", "new")
    if status in ("interested", "qualified"):
        z += _WEIGHTS["engaged_status"]
        reasons.append(f"status is {status}")
    if status == "converted":
        z += _WEIGHTS["converted_status"]
        reasons.append("already converted")

    if getattr(lead, "email", ""):
        z += _WEIGHTS["has_email"]
        reasons.append("has email")

    src = getattr(lead, "source", "unknown") or "unknown"
    sq = _SOURCE_QUALITY.get(src, 0.0)
    z += sq
    if sq >= 0.6:
        reasons.append(f"high-quality source ({src})")
    elif sq <= 0.3:
        reasons.append(f"low-quality source ({src})")

    attempts = getattr(lead, "attempts", 0) or 0
    if attempts > 1:
        z += _WEIGHTS["attempts_penalty"] * (attempts - 1)
        reasons.append(f"{attempts} attempts (fatigue)")

    # Signals from prior call insights.
    for ins in insights or []:
        sent = (getattr(ins, "sentiment", "") or "").lower()
        if sent in ("positive", "warm"):
            z += _WEIGHTS["recent_positive"]
            reasons.append("positive last call")
        objs = getattr(ins, "objections", None) or []
        if objs:
            z += _WEIGHTS["objection_penalty"]
            reasons.append(f"{len(objs)} objection(s) raised")
        summ = (getattr(ins, "summary", "") or "").lower()
        if any(w in summ for w in _POSITIVE):
            z += _WEIGHTS["explicit_intent"]
            reasons.append("expressed buying intent")

    # Existing model close_probability nudges the blend.
    cp = getattr(lead, "close_probability", 0.0) or 0.0
    z += cp * 1.5

    p = round(_sigmoid(z), 3)
    grade = "A" if p >= 0.7 else "B" if p >= 0.45 else "C" if p >= 0.25 else "D"
    return {"propensity": p, "grade": grade, "reasons": reasons[:6]}


def score_and_store(db, lead) -> dict:
    from sqlalchemy import select

    from ..models import CallInsight, LeadScore
    insights = db.scalars(select(CallInsight).where(
        CallInsight.lead_id == lead.id)).all()
    result = score_lead(lead, insights=insights)
    row = db.get(LeadScore, lead.id)
    if row is None:
        db.add(LeadScore(lead_id=lead.id, org_id=getattr(lead, "org_id", ""),
                         propensity=result["propensity"], grade=result["grade"],
                         reasons=result["reasons"]))
    else:
        row.propensity = result["propensity"]
        row.grade = result["grade"]
        row.reasons = result["reasons"]
    db.flush()
    return result


def rank_leads(db, *, org_id: str | None = None, limit: int = 50) -> list[dict]:
    """Return leads ordered hottest-first — the prioritized dial list."""
    from sqlalchemy import select

    from ..models import Lead
    org_id = org_id or settings.default_org_id
    leads = db.scalars(select(Lead).where(
        Lead.org_id == org_id, Lead.suppressed == False)).all()  # noqa: E712
    scored = []
    for lead in leads:
        r = score_and_store(db, lead)
        scored.append({"lead_id": lead.id, "name": lead.name, "phone": lead.phone,
                       "propensity": r["propensity"], "grade": r["grade"],
                       "reasons": r["reasons"]})
    db.flush()
    scored.sort(key=lambda x: x["propensity"], reverse=True)
    return scored[:limit]
