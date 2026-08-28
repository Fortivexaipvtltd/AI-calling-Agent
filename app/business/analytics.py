from __future__ import annotations

from ..config import settings

CONNECTED = ("answered", "completed", "converted", "booked", "human_call_now")
CONVERTED = ("converted", "booked")


def _call_minutes(call) -> float:
    if call.started_at and call.ended_at:
        return max(0.0, (call.ended_at - call.started_at).total_seconds() / 60.0)
    return 1.5  # assume a short attempt when duration is unknown


def call_cost(minutes: float) -> float:
    s = settings
    return round(minutes * (s.cost_twilio_per_min + s.cost_stt_per_min
                            + s.cost_tts_per_min) + s.cost_llm_per_call, 4)


def overview(db) -> dict:
    from sqlalchemy import select

    from ..models import Agent, Call, Lead
    calls = db.scalars(select(Call)).all()
    leads = db.scalars(select(Lead)).all()
    agents = {a.id: a.name for a in db.scalars(select(Agent)).all()}

    total = len(calls)
    connected = [c for c in calls if c.outcome in CONNECTED]
    converted = [c for c in calls if c.outcome in CONVERTED]
    minutes = sum(_call_minutes(c) for c in calls)
    total_cost = sum(call_cost(_call_minutes(c)) for c in calls)

    def _rate(subset, base):
        return round(len(subset) / base, 3) if base else 0.0

    # by rep (agent)
    by_rep: dict[str, dict] = {}
    for c in calls:
        rep = agents.get(c.agent_id, c.agent_id or "unassigned")
        d = by_rep.setdefault(rep, {"calls": 0, "connected": 0, "converted": 0})
        d["calls"] += 1
        d["connected"] += 1 if c.outcome in CONNECTED else 0
        d["converted"] += 1 if c.outcome in CONVERTED else 0
    for d in by_rep.values():
        d["connect_rate"] = _rate([1] * d["connected"], d["calls"])
        d["conversion_rate"] = _rate([1] * d["converted"], d["calls"])

    # by lead source (proxy for "script"/campaign) and language
    by_source: dict[str, int] = {}
    for l in leads:
        by_source[l.source or "unknown"] = by_source.get(l.source or "unknown", 0) + 1

    return {
        "totals": {
            "calls": total,
            "connect_rate": _rate(connected, total),
            "conversion_rate": _rate(converted, total),
            "talk_minutes": round(minutes, 1),
            "avg_call_min": round(minutes / total, 2) if total else 0.0,
            "total_cost_usd": round(total_cost, 2),
            "cost_per_call_usd": round(total_cost / total, 4) if total else 0.0,
            "cost_per_conversion_usd": round(total_cost / len(converted), 2)
            if converted else 0.0,
        },
        "by_rep": by_rep,
        "by_source": by_source,
        "cost_model_per_min_usd": round(
            settings.cost_twilio_per_min + settings.cost_stt_per_min
            + settings.cost_tts_per_min, 4),
    }


def cost_breakdown(db) -> dict:
    """Per-provider spend across all calls (Twilio/Deepgram/ElevenLabs/LLM)."""
    from sqlalchemy import select

    from ..models import Call
    s = settings
    calls = db.scalars(select(Call)).all()
    minutes = sum(_call_minutes(c) for c in calls)
    n = len(calls)
    twilio = round(minutes * s.cost_twilio_per_min, 2)
    stt = round(minutes * s.cost_stt_per_min, 2)
    tts = round(minutes * s.cost_tts_per_min, 2)
    llm = round(n * s.cost_llm_per_call, 2)
    total = round(twilio + stt + tts + llm, 2)
    return {"calls": n, "talk_minutes": round(minutes, 1),
            "twilio_usd": twilio, "deepgram_usd": stt, "elevenlabs_usd": tts,
            "llm_usd": llm, "total_usd": total,
            "cost_per_call_usd": round(total / n, 4) if n else 0.0}


def rep_performance(db) -> list[dict]:
    """Per-agent (rep) leaderboard: calls, connect + conversion rates."""
    from sqlalchemy import select

    from ..models import Agent, Call
    agents = {a.id: a.name for a in db.scalars(select(Agent)).all()}
    calls = db.scalars(select(Call)).all()
    rows: dict[str, dict] = {}
    for c in calls:
        name = agents.get(c.agent_id, c.agent_id or "unassigned")
        d = rows.setdefault(name, {"rep": name, "calls": 0, "connected": 0, "converted": 0})
        d["calls"] += 1
        d["connected"] += 1 if c.outcome in CONNECTED else 0
        d["converted"] += 1 if c.outcome in CONVERTED else 0
    out = []
    for d in rows.values():
        d["connect_rate"] = round(d["connected"] / d["calls"], 3) if d["calls"] else 0.0
        d["conversion_rate"] = round(d["converted"] / d["calls"], 3) if d["calls"] else 0.0
        out.append(d)
    out.sort(key=lambda x: x["conversion_rate"], reverse=True)
    return out


def export_csv(db) -> str:
    """Leadership export: one row per call with lead, rep, outcome, cost."""
    import csv
    import io

    from sqlalchemy import select

    from ..models import Agent, Call, Lead
    agents = {a.id: a.name for a in db.scalars(select(Agent)).all()}
    leads = {l.id: l for l in db.scalars(select(Lead)).all()}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["call_id", "lead", "phone", "rep", "status", "outcome",
                "minutes", "cost_usd", "started_at"])
    for c in db.scalars(select(Call)).all():
        lead = leads.get(c.lead_id)
        mins = _call_minutes(c)
        w.writerow([c.id, lead.name if lead else "", lead.phone if lead else "",
                    agents.get(c.agent_id, c.agent_id or ""), c.status, c.outcome,
                    round(mins, 1), call_cost(mins),
                    c.started_at.isoformat() if c.started_at else ""])
    return buf.getvalue()
