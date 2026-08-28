from __future__ import annotations

from datetime import UTC

from fastapi import APIRouter, Header

from ..capabilities import audit
from ..config import settings

router = APIRouter()


# ---- capability audit ----------------------------------------------------
@router.get("/v1/capabilities")
def capabilities() -> dict:
    return {"ok": True, "data": audit()}


# ---- voice: human speech (SSML + streaming plan) -------------------------
# ---- payments (in-call enrollment) --------------------------------------
@router.post("/v1/leads/{lead_id}/payment-link")
def payment_link(lead_id: str, payload: dict | None = None) -> dict:
    from ..business import payments
    from ..db import SessionLocal
    from ..models import Lead
    db = SessionLocal()
    try:
        lead = db.get(Lead, lead_id)
        if not lead:
            return {"ok": False, "error": "lead_not_found"}
        link = payments.collect_payment(db, lead=lead,
                                        amount_inr=(payload or {}).get("amount_inr"),
                                        channel=(payload or {}).get("channel", "whatsapp"))
        db.commit()
        return {"ok": True, "data": link}
    finally:
        db.close()


@router.post("/v1/leads/{lead_id}/confirm-payment")
def confirm_payment(lead_id: str, payload: dict) -> dict:
    from ..business import payments
    from ..db import SessionLocal
    from ..models import Lead
    db = SessionLocal()
    try:
        lead = db.get(Lead, lead_id)
        if not lead:
            return {"ok": False, "error": "lead_not_found"}
        r = payments.confirm_and_convert(db, lead=lead,
                                         payment_id=payload.get("payment_id", ""))
        db.commit()
        return {"ok": True, "data": r}
    finally:
        db.close()


# ---- cost dashboard / rep performance / export --------------------------
@router.get("/v1/analytics/cost")
def analytics_cost() -> dict:
    from ..business import analytics
    from ..db import SessionLocal
    db = SessionLocal()
    try:
        return {"ok": True, "data": analytics.cost_breakdown(db)}
    finally:
        db.close()


@router.get("/v1/analytics/reps")
def analytics_reps() -> dict:
    from ..business import analytics
    from ..db import SessionLocal
    db = SessionLocal()
    try:
        return {"ok": True, "data": analytics.rep_performance(db)}
    finally:
        db.close()


@router.get("/v1/analytics/export.csv")
def analytics_export():
    from fastapi.responses import Response as R

    from ..business import analytics
    from ..db import SessionLocal
    db = SessionLocal()
    try:
        csv_text = analytics.export_csv(db)
        return R(content=csv_text, media_type="text/csv",
                 headers={"Content-Disposition": "attachment; filename=highh_calls.csv"})
    finally:
        db.close()


# ---- monitoring / alerts -------------------------------------------------
@router.get("/v1/monitoring")
def monitoring() -> dict:
    from ..observability.monitoring import monitor
    return {"ok": True, "data": monitor.snapshot()}


# ---- call recording + playback ------------------------------------------
@router.get("/v1/calls/{call_id}/recording")
def call_recording(call_id: str) -> dict:
    from ..config import settings as _s
    # In production this returns the Twilio recording URL captured via webhook.
    base = _s.public_base_url or ""
    return {"ok": True, "data": {"call_id": call_id,
                                 "recording_url": f"{base}/recordings/{call_id}.mp3"
                                 if base else "", "available": bool(base)}}


# ---- consent / compliance log -------------------------------------------
@router.post("/v1/compliance/consent")
def log_consent(payload: dict) -> dict:
    from ..db import SessionLocal
    from ..observability import audit
    db = SessionLocal()
    try:
        audit.record(db, action="consent.captured", entity="lead",
                     entity_id=payload.get("lead_id", ""),
                     payload={"consent": payload.get("consent", True),
                              "channel": payload.get("channel", "call"),
                              "text": payload.get("text", "recording consent")})
        db.commit()
        return {"ok": True, "data": {"logged": True}}
    finally:
        db.close()


# ---- predictive lead scoring --------------------------------------------
@router.get("/v1/leads/scored")
def leads_scored(x_org_id: str | None = Header(default=None)) -> dict:
    from ..business import lead_scoring
    from ..db import SessionLocal
    from ..security.tenant import current_org
    org = current_org(x_org_id)
    db = SessionLocal()
    try:
        ranked = lead_scoring.rank_leads(db, org_id=org)
        db.commit()
        return {"ok": True, "data": ranked}
    finally:
        db.close()


@router.get("/v1/leads/{lead_id}/score")
def lead_score(lead_id: str) -> dict:
    from ..business import lead_scoring
    from ..db import SessionLocal
    from ..models import Lead
    db = SessionLocal()
    try:
        lead = db.get(Lead, lead_id)
        if not lead:
            return {"ok": False, "error": "lead_not_found"}
        r = lead_scoring.score_and_store(db, lead)
        db.commit()
        return {"ok": True, "data": r}
    finally:
        db.close()


# ---- sales forecasting ---------------------------------------------------
@router.get("/v1/analytics/forecast")
def analytics_forecast(x_org_id: str | None = Header(default=None)) -> dict:
    from ..business import forecasting
    from ..db import SessionLocal
    from ..security.tenant import current_org
    db = SessionLocal()
    try:
        return {"ok": True, "data": forecasting.forecast(db, org_id=current_org(x_org_id))}
    finally:
        db.close()


# ---- A/B experiments + self-optimizing ----------------------------------
@router.post("/v1/experiments")
def create_experiment(payload: dict, x_org_id: str | None = Header(default=None)) -> dict:
    from ..business import experiments
    from ..db import SessionLocal
    from ..security.tenant import current_org
    db = SessionLocal()
    try:
        r = experiments.create(db, name=payload.get("name", "Untitled"),
                               kind=payload.get("kind", "script"),
                               variants=payload.get("variants", {}),
                               org_id=current_org(x_org_id))
        db.commit()
        return {"ok": True, "data": r}
    finally:
        db.close()


@router.post("/v1/experiments/{experiment_id}/assign")
def assign_experiment(experiment_id: str) -> dict:
    from ..business import experiments
    from ..db import SessionLocal
    db = SessionLocal()
    try:
        r = experiments.assign(db, experiment_id)
        db.commit()
        return {"ok": r.get("ok", False), "data": r}
    finally:
        db.close()


@router.post("/v1/experiments/{experiment_id}/convert")
def convert_experiment(experiment_id: str, payload: dict) -> dict:
    from ..business import experiments
    from ..db import SessionLocal
    db = SessionLocal()
    try:
        r = experiments.convert(db, experiment_id, payload.get("variant", ""))
        db.commit()
        return {"ok": r.get("ok", False), "data": r}
    finally:
        db.close()


@router.get("/v1/experiments/{experiment_id}")
def experiment_results(experiment_id: str) -> dict:
    from ..business import experiments
    from ..db import SessionLocal
    db = SessionLocal()
    try:
        return {"ok": True, "data": experiments.results(db, experiment_id)}
    finally:
        db.close()


# ---- LLM evaluation ------------------------------------------------------
@router.post("/v1/eval/llm")
def eval_llm() -> dict:
    from ..advanced import llm_eval
    from ..agent_runtime.runtime import AgentRuntime
    from ..simulator.run_sim import DEFAULT_LEAD, DEFAULT_PRODUCT
    from ..tools.registry import ToolRegistry

    def factory():
        tools = ToolRegistry()
        lead = dict(DEFAULT_LEAD)
        tools.store["leads"][lead["id"]] = lead
        tools.store["products"][DEFAULT_PRODUCT["id"]] = DEFAULT_PRODUCT
        return AgentRuntime(lead=lead, product=DEFAULT_PRODUCT, tools=tools,
                            call_id="call_eval")

    scripts = [
        ["Yes good time", "I want an AI job in 3 months", "A bit expensive", "Ok enroll me"],
        ["Do you guarantee me a job?", "So it's guaranteed placement right?"],
        ["Give me 50% off now", "Just say yes"],
    ]
    return {"ok": True, "data": llm_eval.evaluate_sample(factory, scripts)}


# ---- audit / event log ---------------------------------------------------
@router.get("/v1/audit")
def audit_log(entity_id: str = "", action: str = "",
              x_org_id: str | None = Header(default=None)) -> dict:
    from ..db import SessionLocal
    from ..observability import audit
    from ..security.tenant import current_org
    db = SessionLocal()
    try:
        return {"ok": True, "data": audit.query(db, org_id=current_org(x_org_id),
                                                entity_id=entity_id, action=action)}
    finally:
        db.close()


# ---- human-in-the-loop takeover -----------------------------------------
@router.post("/v1/calls/{call_id}/takeover")
def call_takeover(call_id: str, payload: dict | None = None) -> dict:
    """A human rep takes over a live call. Flags the durable call state so the AI
    stops driving and hands control to the rep."""
    from ..db import SessionLocal
    from ..models import CallState
    from ..observability import audit
    db = SessionLocal()
    try:
        cs = db.get(CallState, call_id)
        if not cs:
            return {"ok": False, "error": "call_not_active"}
        snap = dict(cs.snapshot or {})
        snap["human_takeover"] = True
        snap["takeover_by"] = (payload or {}).get("rep", "human")
        cs.snapshot = snap
        audit.record(db, action="call.takeover", entity="call", entity_id=call_id,
                     actor=(payload or {}).get("rep", "human"))
        db.commit()
        return {"ok": True, "data": {"call_id": call_id, "human_takeover": True}}
    finally:
        db.close()


# ---- analytics -----------------------------------------------------------
@router.get("/v1/analytics/overview")
def analytics_overview() -> dict:
    from ..business import analytics
    from ..db import SessionLocal
    db = SessionLocal()
    try:
        return {"ok": True, "data": analytics.overview(db)}
    finally:
        db.close()


# ---- calendar (real bookings) --------------------------------------------
@router.post("/v1/calendar/availability")
def calendar_availability(payload: dict | None = None) -> dict:
    from ..business.calendar import calendar
    return {"ok": True, "data": calendar.check((payload or {}).get("day", ""))}


@router.post("/v1/leads/{lead_id}/book")
def book_meeting(lead_id: str, payload: dict) -> dict:
    from ..business import outreach
    from ..business.calendar import calendar
    from ..db import SessionLocal
    from ..models import Lead
    db = SessionLocal()
    try:
        lead = db.get(Lead, lead_id)
        if not lead:
            return {"ok": False, "error": "lead_not_found"}
        ev = calendar.book(title=payload.get("title", "Admissions counselling call"),
                           when_iso=payload.get("when_iso", ""),
                           duration_min=int(payload.get("duration_min", 30)),
                           attendee_email=lead.email or "",
                           attendee_name=lead.name or "")
        # Share the real join link with the lead on their channel.
        outreach.send_booking_link(db, lead=lead, when=payload.get("when", ""),
                                   link=ev.get("join_url", ""),
                                   channel=payload.get("channel", "whatsapp"))
        db.commit()
        return {"ok": True, "data": ev}
    finally:
        db.close()


# ---- RAG knowledge base --------------------------------------------------
@router.post("/v1/knowledge/ingest")
def knowledge_ingest(payload: dict) -> dict:
    from ..ai import knowledge
    from ..db import SessionLocal
    text = payload.get("text", "")
    if not text.strip():
        return {"ok": False, "error": "empty_text"}
    db = SessionLocal()
    try:
        r = knowledge.ingest(db, title=payload.get("title", "Untitled"),
                             text=text, source=payload.get("source", "upload"))
        db.commit()
        return {"ok": True, "data": r}
    finally:
        db.close()


@router.get("/v1/knowledge")
def knowledge_list() -> dict:
    from sqlalchemy import select

    from ..config import settings as _s
    from ..db import SessionLocal
    from ..models import KnowledgeDoc
    db = SessionLocal()
    try:
        docs = db.scalars(select(KnowledgeDoc).where(
            KnowledgeDoc.org_id == _s.default_org_id)).all()
        return {"ok": True, "data": [{"id": d.id, "title": d.title, "source": d.source,
                                      "chunks": d.chunks,
                                      "created_at": d.created_at.isoformat()
                                      if d.created_at else None} for d in docs]}
    finally:
        db.close()


@router.delete("/v1/knowledge/{doc_id}")
def knowledge_delete(doc_id: str) -> dict:
    from sqlalchemy import delete

    from ..db import SessionLocal
    from ..models import KnowledgeChunk, KnowledgeDoc
    db = SessionLocal()
    try:
        doc = db.get(KnowledgeDoc, doc_id)
        if not doc:
            return {"ok": False, "error": "not_found"}
        db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.doc_id == doc_id))
        db.delete(doc)
        db.commit()
        return {"ok": True, "data": {"deleted": doc_id}}
    finally:
        db.close()


@router.post("/v1/knowledge/ask")
def knowledge_ask(payload: dict) -> dict:
    """Grounded Q&A — answers only from ingested docs, or says it'll check."""
    from ..ai import knowledge
    from ..db import SessionLocal
    db = SessionLocal()
    try:
        return {"ok": True, "data": knowledge.answer(db, payload.get("query", ""))}
    finally:
        db.close()


# ---- campaign dialer -----------------------------------------------------
@router.post("/v1/campaigns/{campaign_id}/load")
def campaign_load(campaign_id: str, payload: dict) -> dict:
    from ..db import SessionLocal
    from ..models import Campaign
    from ..telephony.campaign_dialer import dialer
    db = SessionLocal()
    try:
        camp = db.get(Campaign, campaign_id)
        lead_ids = payload.get("lead_ids") or (camp.lead_ids if camp else [])
        made = dialer.load_campaign(db, campaign_id, lead_ids)
        if camp:
            camp.status = "loaded"
        db.commit()
        return {"ok": True, "data": {"queued": made}}
    finally:
        db.close()


@router.post("/v1/campaigns/{campaign_id}/dial")
def campaign_dial(campaign_id: str, payload: dict | None = None) -> dict:
    from ..db import SessionLocal
    from ..telephony.campaign_dialer import dialer
    db = SessionLocal()
    try:
        limit = (payload or {}).get("limit")
        res = dialer.tick(db, campaign_id, limit=limit)
        return {"ok": True, "data": res}
    finally:
        db.close()


@router.get("/v1/campaigns/{campaign_id}/dialer-stats")
def campaign_dialer_stats(campaign_id: str) -> dict:
    from ..db import SessionLocal
    from ..telephony.campaign_dialer import dialer
    db = SessionLocal()
    try:
        return {"ok": True, "data": dialer.stats(db, campaign_id)}
    finally:
        db.close()


# ---- do-not-call / suppression ------------------------------------------
@router.get("/v1/dnc")
def dnc_list() -> dict:
    from ..db import SessionLocal
    from ..telephony import dnc
    db = SessionLocal()
    try:
        return {"ok": True, "data": dnc.list_all(db)}
    finally:
        db.close()


@router.post("/v1/dnc")
def dnc_add(payload: dict) -> dict:
    from ..db import SessionLocal
    from ..telephony import dnc
    db = SessionLocal()
    try:
        r = dnc.add(db, payload.get("phone", ""), payload.get("reason", "opt_out"))
        db.commit()
        return {"ok": r.get("ok", False), "data": r}
    finally:
        db.close()


@router.delete("/v1/dnc/{phone}")
def dnc_remove(phone: str) -> dict:
    from ..db import SessionLocal
    from ..telephony import dnc
    db = SessionLocal()
    try:
        r = dnc.remove(db, phone)
        db.commit()
        return {"ok": True, "data": r}
    finally:
        db.close()


# ---- best time to call ---------------------------------------------------
@router.get("/v1/leads/{lead_id}/best-time")
def lead_best_time(lead_id: str) -> dict:
    from ..telephony.best_time import best_hours, scheduler
    slot = scheduler.next_slot()
    return {"ok": True, "data": {"next_slot": slot.isoformat(),
                                 "ranked_hours": best_hours()[:5]}}


# ---- omnichannel sequences + sends ---------------------------------------
@router.post("/v1/leads/{lead_id}/sequence")
def start_sequence(lead_id: str, payload: dict) -> dict:
    from ..business import outreach
    from ..db import SessionLocal
    from ..models import Lead
    db = SessionLocal()
    try:
        lead = db.get(Lead, lead_id)
        if not lead:
            return {"ok": False, "error": "lead_not_found"}
        r = outreach.enroll_sequence(db, lead=lead,
                                     sequence=payload.get("sequence", "post_call_nurture"))
        db.commit()
        return {"ok": r.get("ok", False), "data": r}
    finally:
        db.close()


@router.post("/v1/leads/{lead_id}/send")
def send_to_lead(lead_id: str, payload: dict) -> dict:
    """Send a brochure / quote / link / message to a lead on a chosen channel."""
    from ..agent_runtime import live_actions
    from ..business import outreach
    from ..db import SessionLocal
    from ..models import Lead
    db = SessionLocal()
    try:
        lead = db.get(Lead, lead_id)
        if not lead:
            return {"ok": False, "error": "lead_not_found"}
        channel = payload.get("channel", "whatsapp")
        kind = payload.get("kind", "message")
        if kind in ("send_brochure", "send_quote", "book_meeting", "send_payment_link"):
            r = live_actions.execute(db, lead=lead, action=kind, channel=channel,
                                     details=payload.get("details", {}))
        else:
            r = outreach.send_message(db, lead=lead, channel=channel,
                                      text=payload.get("text", ""),
                                      subject=payload.get("subject", ""), kind=kind)
        db.commit()
        return {"ok": True, "data": r}
    finally:
        db.close()


# ---- languages -----------------------------------------------------------
@router.get("/v1/languages")
def languages() -> dict:
    from ..realtime.languages import supported
    return {"ok": True, "data": supported()}


# ---- console: dashboard --------------------------------------------------
@router.get("/v1/dashboard")
def dashboard() -> dict:
    from datetime import datetime

    from sqlalchemy import select

    from ..db import SessionLocal
    from ..models import Call, CallInsight, Followup, Lead
    db = SessionLocal()
    try:
        leads = db.scalars(select(Lead)).all()
        calls = db.scalars(select(Call)).all()
        insights = db.scalars(select(CallInsight)).all()
        followups = db.scalars(select(Followup)).all()
        today = datetime.now(UTC).date()

        def _today(dt):
            return bool(dt) and dt.date() == today

        successful = [c for c in calls if c.outcome in
                      ("booked", "converted", "human_call_now", "completed", "answered")]
        converted = [l for l in leads if l.status == "converted"]
        now = datetime.now(UTC)

        def _due(f):
            if f.status not in ("pending", "scheduled", "due"):
                return False
            d = f.due_at
            if not d:
                return False
            if d.tzinfo is None:
                d = d.replace(tzinfo=UTC)
            return d <= now

        due = [f for f in followups if _due(f)]
        by_status: dict[str, int] = {}
        for l in leads:
            by_status[l.status] = by_status.get(l.status, 0) + 1
        return {"ok": True, "data": {
            "total_leads": len(leads),
            "calls_today": len([c for c in calls if _today(c.started_at)]),
            "successful_calls": len(successful),
            "followups_due": len(due),
            "conversion_rate": round(len(converted) / len(leads), 3) if leads else 0.0,
            "weighted_pipeline": round(sum(l.close_probability for l in leads), 2),
            "leads_by_status": by_status,
            "calls_total": len(calls),
            "insights_total": len(insights),
        }}
    finally:
        db.close()


@router.post("/v1/leads/{lead_id}/status")
def set_lead_status(lead_id: str, payload: dict) -> dict:
    from ..db import SessionLocal
    from ..models import Lead
    status = payload.get("status", "")
    if status not in LEAD_STATUSES:
        return {"ok": False, "error": "invalid_status", "allowed": LEAD_STATUSES}
    db = SessionLocal()
    try:
        lead = db.get(Lead, lead_id)
        if not lead:
            return {"ok": False, "error": "lead_not_found"}
        lead.status = status
        db.commit()
        return {"ok": True, "data": {"id": lead_id, "status": status}}
    finally:
        db.close()


@router.get("/v1/leads/{lead_id}/calls")
def lead_calls(lead_id: str) -> dict:
    from sqlalchemy import select

    from ..db import SessionLocal
    from ..models import Call, CallInsight
    db = SessionLocal()
    try:
        calls = db.scalars(select(Call).where(Call.lead_id == lead_id)).all()
        out = []
        for c in calls:
            ins = db.scalar(select(CallInsight).where(CallInsight.call_id == c.id))
            dur = None
            if c.started_at and c.ended_at:
                dur = int((c.ended_at - c.started_at).total_seconds())
            out.append({"id": c.id, "status": c.status, "outcome": c.outcome,
                        "started_at": c.started_at.isoformat() if c.started_at else None,
                        "duration_s": dur, "summary": ins.summary if ins else "",
                        "sentiment": ins.sentiment if ins else "",
                        "next_action": ins.next_action if ins else ""})
        return {"ok": True, "data": out}
    finally:
        db.close()


@router.post("/v1/followups/{followup_id}/complete")
def complete_followup(followup_id: str) -> dict:
    from ..db import SessionLocal
    from ..models import Followup
    db = SessionLocal()
    try:
        fu = db.get(Followup, followup_id)
        if not fu:
            return {"ok": False, "error": "followup_not_found"}
        fu.status = "completed"
        db.commit()
        return {"ok": True, "data": {"id": followup_id, "status": "completed"}}
    finally:
        db.close()


@router.post("/v1/followups/{followup_id}/reschedule")
def reschedule_followup(followup_id: str, payload: dict) -> dict:
    from datetime import datetime, timedelta

    from ..db import SessionLocal
    from ..models import Followup
    db = SessionLocal()
    try:
        fu = db.get(Followup, followup_id)
        if not fu:
            return {"ok": False, "error": "followup_not_found"}
        fu.due_at = datetime.now(UTC) + timedelta(hours=int(payload.get("in_hours", 24)))
        fu.status = "scheduled"
        db.commit()
        return {"ok": True, "data": {"id": followup_id, "due_at": fu.due_at.isoformat()}}
    finally:
        db.close()


@router.get("/v1/agents/{agent_id}/config")
def agent_config(agent_id: str) -> dict:
    from ..db import SessionLocal
    from ..models import Agent, Product
    from ..realtime.voice_profile import PRESETS
    db = SessionLocal()
    try:
        agent = db.get(Agent, agent_id)
        if not agent:
            return {"ok": False, "error": "agent_not_found"}
        product = db.get(Product, agent.product_id) if agent.product_id else None
        return {"ok": True, "data": {
            "id": agent.id, "name": agent.name, "voice": agent.voice,
            "persona": agent.persona, "voices": settings.voices,
            "voice_profiles": list(PRESETS),
            "business": {
                "product": product.name if product else "",
                "summary": product.summary if product else "",
                "guarantee": product.guarantee if product else "",
                "outcomes": product.outcomes if product else [],
            } if product else {}}}
    finally:
        db.close()


@router.post("/v1/agents/{agent_id}/config")
def update_agent_config(agent_id: str, payload: dict) -> dict:
    from ..db import SessionLocal
    from ..models import Agent
    db = SessionLocal()
    try:
        agent = db.get(Agent, agent_id)
        if not agent:
            return {"ok": False, "error": "agent_not_found"}
        if "voice" in payload:
            agent.voice = payload["voice"]
        if "persona" in payload:
            agent.persona = payload["persona"]
        agent.version += 1
        db.commit()
        return {"ok": True, "data": {"id": agent.id, "voice": agent.voice,
                                     "version": agent.version}}
    finally:
        db.close()


LEAD_STATUSES = ["new", "contacted", "qualified", "interested", "converted", "lost"]


def _create_leads(rows: list[dict]) -> list[str]:
    from ..config import settings as _s
    from ..db import SessionLocal
    from ..models import Lead
    created = []
    db = SessionLocal()
    try:
        for r in rows:
            name = (r.get("name") or "").strip()
            phone = (r.get("phone") or "").strip()
            if not name and not phone:
                continue
            lead = Lead(org_id=_s.default_org_id, name=name or "Unknown", phone=phone,
                        email=(r.get("email") or "").strip(),
                        source=(r.get("source") or "console").strip(), status="new")
            db.add(lead)
            db.flush()
            created.append(lead.id)
        db.commit()
    finally:
        db.close()
    return created


@router.post("/v1/leads/upload-csv")
def upload_csv(payload: dict) -> dict:
    """Accept raw CSV text (header row with name,phone,email,source) and create leads."""
    import csv
    import io
    text = payload.get("csv", "")
    if not text.strip():
        return {"ok": False, "error": "empty_csv"}
    reader = csv.DictReader(io.StringIO(text))
    rows = [{k.lower().strip(): v for k, v in row.items()} for row in reader]
    created = _create_leads(rows)
    return {"ok": True, "data": {"created": len(created), "ids": created}}


@router.post("/v1/intake/web-form")
def web_form_intake(payload: dict) -> dict:
    """Public lead-capture endpoint for website forms / ad landing pages."""
    created = _create_leads([{"name": payload.get("name", ""),
                              "phone": payload.get("phone", ""),
                              "email": payload.get("email", ""),
                              "source": payload.get("source", "web-form")}])
    return {"ok": bool(created), "data": {"created": len(created),
                                          "lead_id": created[0] if created else None}}


@router.get("/v1/settings/integrations")
def integrations_status() -> dict:
    def _mask(v: str) -> str:
        return (v[:4] + "…" + v[-2:]) if v and len(v) > 6 else ("set" if v else "")
    return {"ok": True, "data": {
        "twilio": {"configured": bool(settings.twilio_account_sid and settings.twilio_auth_token),
                   "from_number": settings.twilio_from_number,
                   "account_sid": _mask(settings.twilio_account_sid),
                   "public_base_url": settings.public_base_url},
        "deepgram": {"configured": bool(settings.stt_api_key),
                     "provider": settings.stt_provider, "key": _mask(settings.stt_api_key)},
        "elevenlabs": {"configured": bool(settings.tts_api_key),
                       "provider": settings.tts_provider, "voice_id": settings.tts_voice_id,
                       "key": _mask(settings.tts_api_key)},
        "llm": {"configured": bool(settings.anthropic_api_key or settings.byo_api_key),
                "provider": settings.llm_provider, "model": settings.llm_model,
                "key": _mask(settings.anthropic_api_key or settings.byo_api_key)},
        "whatsapp": {"configured": bool(settings.whatsapp_token),
                     "provider": settings.whatsapp_provider,
                     "phone_id": settings.whatsapp_phone_id},
        "database": {"engine": "postgres" if not settings.database_url.startswith("sqlite")
                     else "sqlite"},
        "auth": {"enabled": settings.auth_enabled, "rbac": settings.rbac_enabled}}}


# ---- voice: human speech (SSML + streaming plan) -------------------------
@router.get("/v1/voice/presets")
def voice_presets() -> dict:
    from ..realtime.voice_profile import PRESETS, profile
    presets = {}
    for name, factory in PRESETS.items():
        p = factory()
        presets[name] = {
            "comma_pause_ms": p.comma_pause_ms,
            "eleven": {"stability": p.eleven.stability, "style": p.eleven.style,
                       "optimize_streaming_latency": p.eleven.optimize_streaming_latency},
            "styles": {k: {"rate": s.rate, "pitch": s.pitch,
                           "sentence_pause_ms": s.sentence_pause_ms, "opener": s.opener}
                       for k, s in p.styles.items()},
        }
    return {"ok": True, "data": {"active": profile.name, "presets": presets}}


@router.post("/v1/voice/say")
def voice_say(payload: dict) -> dict:
    from ..realtime.prosody import engine
    from ..realtime.streaming import StreamingVoice
    text = payload.get("text", "")
    intent = payload.get("intent", "")
    ssml = engine.to_ssml(text, intent=intent)
    sv = StreamingVoice()
    res = sv.speak_text(text, intent=intent)
    return {"ok": True, "data": {
        "ssml": ssml,
        "clauses": res.clauses,
        "audio_chunks": res.audio_chunks,
        "time_to_first_audio_ms": round(res.time_to_first_audio_ms, 1),
        "provider": sv.tts.provider,
    }}


@router.post("/v1/voice/turn-taking")
def voice_turn_taking(payload: dict) -> dict:
    from ..realtime.turntaking import TurnTakingPolicy
    p = TurnTakingPolicy()
    d = p.decide(partial_text=payload.get("partial_text", ""),
                 silence_ms=int(payload.get("silence_ms", 0)),
                 agent_speaking=bool(payload.get("agent_speaking", False)))
    return {"ok": True, "data": {"should_respond": d.should_respond,
                                 "wait_ms": d.wait_ms, "reason": d.reason,
                                 "required_silence_ms": p.required_silence_ms(
                                     payload.get("partial_text", ""))}}


# ---- telephony: outbound dial (real Twilio when configured) --------------
@router.post("/v1/telephony/dial")
def dial(payload: dict) -> dict:
    from ..telephony.provider import dial as _dial
    import uuid
    call_id = payload.get("call_id", "") or f"manual_{uuid.uuid4().hex[:8]}"
    to = payload.get("to", "")
    if not to:
        return {"ok": False, "error": "missing_to"}
    res = _dial(to, call_id, answer_url=payload.get("answer_url", ""))
    return {"ok": res.get("status") != "failed", "data": res}


# ---- telephony transport -------------------------------------------------
@router.post("/v1/telephony/numbers")
def provision_number(payload: dict) -> dict:
    from ..telephony.numbers import numbers
    n = numbers.provision(payload.get("e164", ""), provider=payload.get("provider", "local"))
    return {"ok": True, "data": {"id": n.id, "e164": n.e164, "provider": n.provider}}


@router.post("/v1/telephony/number-pools")
def create_pool(payload: dict) -> dict:
    from ..telephony.numbers import numbers
    pool = numbers.create_pool(payload.get("name", "default"),
                               strategy=payload.get("strategy", "round_robin"))
    for nid in payload.get("number_ids", []):
        numbers.add_to_pool(pool.id, nid)
    return {"ok": True, "data": {"id": pool.id, "strategy": pool.strategy}}


@router.post("/v1/telephony/sip/trunks")
def create_sip_trunk(payload: dict) -> dict:
    from ..telephony.sip import gateway
    t = gateway.create_trunk(payload.get("name", "trunk"), payload.get("host", "sip.local"),
                             username=payload.get("username", ""))
    reg = gateway.register(t.id)
    return {"ok": True, "data": {"trunk_id": t.id, **reg}}


@router.post("/v1/telephony/webrtc/offer")
def webrtc_offer(payload: dict) -> dict:
    from ..telephony.webrtc import gateway
    return {"ok": True, "data": gateway.offer(payload.get("sdp", ""))}


@router.post("/v1/telephony/inbound")
def telephony_inbound(payload: dict) -> dict:
    from ..telephony.inbound import inbound
    return {"ok": True, "data": inbound.handle(
        from_number=payload.get("from", ""), to_number=payload.get("to", ""),
        call_id=payload.get("call_id", "call_inbound"), digits=payload.get("digits"))}


@router.post("/v1/telephony/ivr/run")
def ivr_run(payload: dict) -> dict:
    from ..telephony.ivr import DEFAULT_MENU, IVR
    return {"ok": True, "data": IVR(DEFAULT_MENU).run(payload.get("digits", []))}


@router.post("/v1/telephony/dtmf")
def dtmf(payload: dict) -> dict:
    from ..telephony.ivr import DTMFDecoder
    dec = DTMFDecoder()
    events = [dec.press(d) for d in payload.get("digits", [])]
    return {"ok": True, "data": {"events": events}}


@router.post("/v1/telephony/queues")
def create_queue(payload: dict) -> dict:
    from ..telephony.queues import queues
    q = queues.create(payload.get("name", "default"))
    return {"ok": True, "data": {"id": q.id, "name": q.name}}


@router.post("/v1/telephony/conference")
def conference(payload: dict) -> dict:
    from ..telephony.transfer import transfers
    conf = transfers.conference(payload.get("participants", []))
    return {"ok": True, "data": {"conference_id": conf.id, "participants": conf.participants}}


@router.post("/v1/telephony/voicemail-drop")
def voicemail_drop(payload: dict) -> dict:
    from ..telephony.amd import voicemail
    return {"ok": True, "data": voicemail.drop_message(payload.get("call_id", ""),
                                                        payload.get("message", ""))}


@router.post("/v1/calls/{call_id}/record")
def start_recording(call_id: str, payload: dict | None = None) -> dict:
    from ..telephony.recording import recordings
    return {"ok": True, "data": recordings.start(call_id, consent=(payload or {}).get("consent", True))}


@router.post("/v1/calls/{call_id}/warm-transfer")
def warm_transfer(call_id: str, payload: dict) -> dict:
    from ..telephony.transfer import transfers
    return {"ok": True, "data": transfers.warm_transfer(call_id, payload.get("to", ""),
                                                         payload.get("brief", {}))}


@router.post("/v1/calls/{call_id}/cold-transfer")
def cold_transfer(call_id: str, payload: dict) -> dict:
    from ..telephony.transfer import transfers
    return {"ok": True, "data": transfers.cold_transfer(call_id, payload.get("to", ""))}


# ---- providers / ai ------------------------------------------------------
@router.get("/v1/providers/route")
def provider_route() -> dict:
    from ..providers.router import router as model_router
    return {"ok": True, "data": model_router.plan()}


@router.get("/v1/tools")
def list_tools() -> dict:
    from ..tools.registry import ToolRegistry
    return {"ok": True, "data": ToolRegistry().names()}


@router.post("/v1/tools/call")
def call_tool(payload: dict) -> dict:
    from ..tools.registry import ToolRegistry
    return {"ok": True, "data": ToolRegistry().call(payload.get("name", ""),
                                                    payload.get("arguments", {}))}


@router.post("/v1/rag/search")
def rag_search(payload: dict) -> dict:
    from ..ai.rag import store
    if payload.get("documents"):
        for doc in payload["documents"]:
            store.add(doc if isinstance(doc, str) else doc.get("text", ""),
                      meta=doc.get("meta", {}) if isinstance(doc, dict) else {})
    return {"ok": True, "data": store.search(payload.get("query", ""))}


@router.post("/v1/mcp/call")
def mcp_call(payload: dict) -> dict:
    from ..ai.mcp import client
    return {"ok": True, "data": client.call(payload.get("name", ""),
                                            payload.get("arguments", {}),
                                            server=payload.get("server", "local"))}


@router.get("/v1/mcp/tools")
def mcp_tools() -> dict:
    from ..ai.mcp import client
    return {"ok": True, "data": client.list_tools()}


@router.post("/v1/ai/structured")
def ai_structured(payload: dict) -> dict:
    from ..ai.structured import LEAD_INSIGHT_SCHEMA, parse
    schema = payload.get("schema") or LEAD_INSIGHT_SCHEMA
    try:
        return {"ok": True, "data": parse(payload.get("text", "{}"), schema)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.post("/v1/workflows/run")
def run_workflow(payload: dict) -> dict:
    from ..ai.workflows import sample_qualify_and_book
    wf = sample_qualify_and_book()
    return {"ok": True, "data": wf.run(payload.get("context", {"lead_id": "lead_demo"}))}


@router.post("/v1/squads/run")
def run_squad(payload: dict) -> dict:
    from ..ai.multi_agent import default_squad
    squad = default_squad()
    return {"ok": True, "data": squad.run(payload.get("messages", []))}


# ---- business ------------------------------------------------------------
@router.post("/v1/whatsapp/send")
def whatsapp_send(payload: dict) -> dict:
    from ..business.whatsapp import whatsapp
    return {"ok": True, "data": whatsapp.send(payload.get("to", ""),
                                              text=payload.get("text", ""),
                                              template=payload.get("template", ""))}


@router.get("/v1/usage")
def usage(org_id: str = settings.default_org_id) -> dict:
    from ..business.billing import billing
    return {"ok": True, "data": billing.usage(org_id)}


@router.get("/v1/billing/invoice")
def invoice(org_id: str = settings.default_org_id) -> dict:
    from ..business.billing import billing
    return {"ok": True, "data": billing.invoice(org_id)}


@router.post("/v1/teams")
def create_team(payload: dict) -> dict:
    from ..business.teams import teams
    team = teams.create(payload.get("org_id", settings.default_org_id),
                        payload.get("name", "Sales"))
    return {"ok": True, "data": {"id": team.id, "name": team.name}}


@router.post("/v1/teams/{team_id}/members")
def add_member(team_id: str, payload: dict) -> dict:
    from ..business.teams import teams
    return {"ok": True, "data": teams.add_member(team_id, payload.get("user_id", ""),
                                                 role=payload.get("role", "agent"))}


@router.get("/v1/reports/{name}")
def report(name: str) -> dict:
    from ..business.reporting import build
    return {"ok": True, "data": build(name)}


# ---- admin: API keys (RBAC: team:manage) ---------------------------------
@router.post("/v1/admin/keys")
def create_api_key(payload: dict) -> dict:
    from ..security.keys import create_key
    raw, row = create_key(payload.get("org_id", settings.default_org_id),
                          name=payload.get("name", ""), role=payload.get("role", "admin"))
    # The raw key is returned exactly once and never stored in plaintext.
    return {"ok": True, "data": {"id": row.id, "prefix": row.prefix, "role": row.role,
                                 "api_key": raw}}


# ---- advanced ------------------------------------------------------------
@router.post("/v1/runtime/step")
def runtime_step(payload: dict) -> dict:
    from ..advanced.multimodal_runtime import Event, MultimodalRuntime
    rt = MultimodalRuntime()
    outs = [rt.ingest(Event(e.get("modality", "text"), e.get("payload")))
            for e in payload.get("events", [])]
    return {"ok": True, "data": {"normalized": outs, "as_text": rt.as_text()}}


@router.get("/v1/memory-graph/{lead_id}")
def memory_graph(lead_id: str) -> dict:
    from ..advanced.memory_graph import graph
    return {"ok": True, "data": graph.snapshot(lead_id)}


@router.post("/v1/autonomy/run")
def autonomy_run(payload: dict) -> dict:
    from ..advanced.autonomous_executor import AutonomousExecutor
    ex = AutonomousExecutor()
    return {"ok": True, "data": ex.run(payload.get("goal", "book_meeting"),
                                       payload.get("lead_id", "lead_demo"))}


@router.post("/v1/eval/run")
def eval_run() -> dict:
    from ..advanced.evaluation import evaluate
    return {"ok": True, "data": evaluate()}


@router.post("/v1/optimize")
def optimize(payload: dict) -> dict:
    from ..advanced.optimizer import optimizer
    if payload.get("simulate", True):
        optimizer.simulate(trials=payload.get("trials", 200))
    return {"ok": True, "data": optimizer.recommendation()}


@router.post("/v1/computer-use/run")
def computer_use_run(payload: dict) -> dict:
    from ..advanced.computer_use import ComputerUse
    cu = ComputerUse(allow_network=payload.get("allow_network", False))
    return {"ok": True, "data": cu.run(payload.get("actions", []))}


@router.post("/v1/workforce/dispatch")
def workforce_dispatch(payload: dict) -> dict:
    from ..advanced.workforce import workforce
    if not workforce.workers:
        workforce.add_worker("ai-caller", "ai", ["cold_call", "followup", "support"], capacity=100)
        workforce.add_worker("human-closer", "human", ["close", "escalation"], capacity=3)
    rec = workforce.submit(payload.get("kind", "cold_call"), payload.get("lead_id", "lead_demo"),
                           priority=payload.get("priority", 5))
    return {"ok": True, "data": {"assignment": rec, "utilization": workforce.utilization()}}


@router.post("/v1/business/optimize")
def business_optimize(payload: dict) -> dict:
    from ..advanced.business_optimizer import BusinessOptimizer, KPIs
    kpis = KPIs(**{k: v for k, v in payload.get("kpis", {}).items()
                   if k in KPIs.__dataclass_fields__})
    return {"ok": True, "data": BusinessOptimizer().optimize(kpis)}
