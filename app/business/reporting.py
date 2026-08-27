from __future__ import annotations

import csv
import io

from sqlalchemy import select

from ..db import SessionLocal
from ..models import Call, CallInsight, Followup, Lead


def _rows_leads() -> list[dict]:
    db = SessionLocal()
    try:
        leads = db.scalars(select(Lead)).all()
        return [{"id": l.id, "name": l.name, "stage": l.stage, "score": l.score,
                 "close_probability": l.close_probability, "status": l.status,
                 "suppressed": l.suppressed} for l in leads]
    finally:
        db.close()


def _rows_calls() -> list[dict]:
    db = SessionLocal()
    try:
        calls = db.scalars(select(Call)).all()
        return [{"id": c.id, "lead_id": c.lead_id, "status": c.status,
                 "outcome": c.outcome} for c in calls]
    finally:
        db.close()


def pipeline_report() -> dict:
    rows = _rows_leads()
    by_stage: dict[str, int] = {}
    weighted = 0.0
    for r in rows:
        by_stage[r["stage"]] = by_stage.get(r["stage"], 0) + 1
        weighted += r["close_probability"]
    return {"report": "pipeline", "total_leads": len(rows), "by_stage": by_stage,
            "weighted_pipeline": round(weighted, 2), "rows": rows}


def outcomes_report() -> dict:
    db = SessionLocal()
    try:
        insights = db.scalars(select(CallInsight)).all()
        sentiments: dict[str, int] = {}
        actions: dict[str, int] = {}
        for i in insights:
            sentiments[i.sentiment] = sentiments.get(i.sentiment, 0) + 1
            actions[i.next_action] = actions.get(i.next_action, 0) + 1
        return {"report": "outcomes", "calls_analyzed": len(insights),
                "by_sentiment": sentiments, "by_next_action": actions}
    finally:
        db.close()


def followups_report() -> dict:
    db = SessionLocal()
    try:
        fus = db.scalars(select(Followup)).all()
        by_status: dict[str, int] = {}
        for f in fus:
            by_status[f.status] = by_status.get(f.status, 0) + 1
        return {"report": "followups", "total": len(fus), "by_status": by_status}
    finally:
        db.close()


REPORTS = {
    "pipeline": pipeline_report,
    "outcomes": outcomes_report,
    "followups": followups_report,
}


def build(name: str) -> dict:
    fn = REPORTS.get(name)
    if not fn:
        return {"error": f"unknown_report:{name}", "available": sorted(REPORTS)}
    return fn()


def to_csv(name: str) -> str:
    """Export a report's rows as CSV (leads/calls)."""
    rows = _rows_leads() if name == "pipeline" else _rows_calls()
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()
