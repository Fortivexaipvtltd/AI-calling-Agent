from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from . import errors as error_handlers
from .compliance import check_call_permission
from .config import settings
from .db import get_db, init_db
from .events import bus
from .models import (
    Activity,
    Agent,
    Call,
    CallInsight,
    Campaign,
    Conversation,
    ConversationMessage,
    Followup,
    Lead,
    Product,
)
from .observability.logging import configure_logging, log
from .observability.metrics import metrics
from .providers.stt import STTProvider
from .providers.tts import TTSProvider
from .routers.extensions import router as extensions_router
from .scheduler import run_due, scheduler
from .schemas import (
    AgentIn,
    AgentPatch,
    CalendarBook,
    CalendarCheck,
    CallIn,
    CampaignIn,
    FollowupIn,
    LeadImport,
    LeadPatch,
    Ok,
    SimulateIn,
    TurnIn,
)
from .security.auth import get_principal
from .security.middleware import RequestContextMiddleware
from .seed import seed
from .service import (
    build_runtime,
    deactivate_call_state,
    finalize_call,
    load_runtime,
    persist_conversation,
    persist_turn,
    save_call_state,
)
from .simulator.run_sim import run as run_sim
from .tools.registry import ToolRegistry

configure_logging()

app = FastAPI(title=settings.app_name, version="1.0.0")

# Global auth: every /v1 route requires a principal. When AUTH_ENABLED=0 the
# dependency returns a dev principal, so local/dev/tests are unaffected.
app.include_router(extensions_router, dependencies=[Depends(get_principal)])

# Twilio webhooks authenticate via request signature, not our API key, so they
# are mounted WITHOUT the bearer-auth dependency.
from .routers.telephony_webhooks import router as twilio_router  # noqa: E402

app.include_router(twilio_router)

error_handlers.register(app)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list(),
    allow_credentials=("*" not in settings.cors_list()),
    allow_methods=["*"],
    allow_headers=["*"],
)
if settings.trusted_host_list() != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list())

_WEB = Path(__file__).parent / "web"


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def console() -> HTMLResponse:
    index = _WEB / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Highh</h1><p>Console not found.</p>", status_code=404)


# live in-memory runtimes for interactive calls
_LIVE: dict[str, dict] = {}


@app.on_event("startup")
def _startup() -> None:
    problems = settings.validate()
    if problems:
        msg = "invalid production configuration: " + "; ".join(problems)
        if settings.is_production:
            raise RuntimeError(msg)   # fail fast instead of booting insecure
        log.warning(msg)
    init_db()
    ids = seed()
    app.state.seed = ids
    if settings.scheduler_enabled:
        scheduler.start()
    log.info("startup_complete", extra={"path": "-"})


@app.on_event("shutdown")
def _shutdown() -> None:
    scheduler.stop()


@app.get("/health")
def health() -> dict:
    # Liveness: process is up. Never touches dependencies.
    return {"ok": True, "service": settings.app_name, "env": settings.env}


@app.get("/ready")
def ready() -> dict:
    # Readiness: verify the database round-trips before taking traffic.
    try:
        for db in [next(get_db())]:
            db.execute(text("SELECT 1"))
        return {"ok": True, "checks": {"database": "ok"}}
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=503, detail=f"not_ready:{exc}") from exc


@app.get("/metrics", response_class=PlainTextResponse)
def metrics_endpoint() -> str:
    return metrics.render()


# ---- leads ---------------------------------------------------------------
@app.post("/v1/leads/import")
def import_leads(body: LeadImport, db: Session = Depends(get_db)) -> Ok:
    org_id = app.state.seed["org_id"]
    created = []
    for item in body.leads:
        lead = Lead(org_id=org_id, name=item.name, phone=item.phone,
                    email=item.email, source=item.source)
        db.add(lead)
        db.flush()
        bus.emit("lead.created", {"lead_id": lead.id})
        created.append(lead.id)
    db.commit()
    return Ok(data={"created": created})


@app.get("/v1/leads")
def list_leads(db: Session = Depends(get_db)) -> Ok:
    leads = db.scalars(select(Lead)).all()
    return Ok(data=[{"id": l.id, "name": l.name, "phone": l.phone, "status": l.status,
                     "stage": l.stage, "score": l.score, "suppressed": l.suppressed}
                    for l in leads])


@app.get("/v1/leads/{lead_id}")
def get_lead(lead_id: str, db: Session = Depends(get_db)) -> Ok:
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "lead_not_found")
    facts = {f.key: f.value for f in lead.facts}
    return Ok(data={"id": lead.id, "name": lead.name, "phone": lead.phone,
                    "status": lead.status, "stage": lead.stage, "score": lead.score,
                    "close_probability": lead.close_probability, "facts": facts,
                    "suppressed": lead.suppressed})


@app.patch("/v1/leads/{lead_id}")
def patch_lead(lead_id: str, body: LeadPatch, db: Session = Depends(get_db)) -> Ok:
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "lead_not_found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(lead, k, v)
    db.commit()
    return Ok(data={"id": lead.id})


@app.post("/v1/leads/{lead_id}/suppress")
def suppress_lead(lead_id: str, db: Session = Depends(get_db)) -> Ok:
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "lead_not_found")
    lead.suppressed = True
    db.commit()
    bus.emit("lead.suppressed", {"lead_id": lead_id})
    return Ok(data={"id": lead_id, "suppressed": True})


# ---- agents --------------------------------------------------------------
@app.post("/v1/agents")
def create_agent(body: AgentIn, db: Session = Depends(get_db)) -> Ok:
    agent = Agent(org_id=app.state.seed["org_id"], name=body.name, product_id=body.product_id,
                  playbook_id=body.playbook_id, voice=body.voice, persona=body.persona)
    db.add(agent)
    db.commit()
    return Ok(data={"id": agent.id})


@app.get("/v1/agents")
def list_agents(db: Session = Depends(get_db)) -> Ok:
    agents = db.scalars(select(Agent)).all()
    return Ok(data=[{"id": a.id, "name": a.name, "voice": a.voice} for a in agents])


@app.patch("/v1/agents/{agent_id}")
def patch_agent(agent_id: str, body: AgentPatch, db: Session = Depends(get_db)) -> Ok:
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(404, "agent_not_found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(agent, k, v)
    db.commit()
    return Ok(data={"id": agent.id})


@app.post("/v1/agents/{agent_id}/test")
def test_agent(agent_id: str, body: SimulateIn, db: Session = Depends(get_db)) -> Ok:
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(404, "agent_not_found")
    product = db.get(Product, agent.product_id)
    from .service import product_to_dict
    result = run_sim(body.prospect, product=product_to_dict(product))
    return Ok(data=result)


# ---- campaigns -----------------------------------------------------------
@app.post("/v1/campaigns")
def create_campaign(body: CampaignIn, db: Session = Depends(get_db)) -> Ok:
    camp = Campaign(org_id=app.state.seed["org_id"], name=body.name,
                    agent_id=body.agent_id, lead_ids=body.lead_ids)
    db.add(camp)
    db.commit()
    return Ok(data={"id": camp.id})


@app.get("/v1/campaigns")
def list_campaigns(db: Session = Depends(get_db)) -> Ok:
    camps = db.scalars(select(Campaign)).all()
    return Ok(data=[{"id": c.id, "name": c.name, "status": c.status} for c in camps])


@app.get("/v1/campaigns/{campaign_id}")
def get_campaign(campaign_id: str, db: Session = Depends(get_db)) -> Ok:
    camp = db.get(Campaign, campaign_id)
    if not camp:
        raise HTTPException(404, "campaign_not_found")
    return Ok(data={"id": camp.id, "name": camp.name, "status": camp.status,
                    "lead_ids": camp.lead_ids})


def _set_campaign_status(campaign_id: str, status: str, db: Session) -> Ok:
    camp = db.get(Campaign, campaign_id)
    if not camp:
        raise HTTPException(404, "campaign_not_found")
    camp.status = status
    db.commit()
    if status == "running":
        bus.emit("campaign.started", {"campaign_id": campaign_id})
    return Ok(data={"id": campaign_id, "status": status})


@app.post("/v1/campaigns/{campaign_id}/start")
def start_campaign(campaign_id: str, db: Session = Depends(get_db)) -> Ok:
    return _set_campaign_status(campaign_id, "running", db)


@app.post("/v1/campaigns/{campaign_id}/pause")
def pause_campaign(campaign_id: str, db: Session = Depends(get_db)) -> Ok:
    return _set_campaign_status(campaign_id, "paused", db)


@app.post("/v1/campaigns/{campaign_id}/resume")
def resume_campaign(campaign_id: str, db: Session = Depends(get_db)) -> Ok:
    return _set_campaign_status(campaign_id, "running", db)


# ---- calls ---------------------------------------------------------------
@app.post("/v1/calls")
def create_call(body: CallIn, db: Session = Depends(get_db)) -> Ok:
    lead = db.get(Lead, body.lead_id)
    agent = db.get(Agent, body.agent_id)
    if not lead or not agent:
        raise HTTPException(404, "lead_or_agent_not_found")

    allowed, reason = check_call_permission(lead, datetime.now())
    if not allowed:
        raise HTTPException(403, f"compliance_block:{reason}")

    lead.attempts += 1
    rt, call, tools = build_runtime(db, lead, agent)
    opening = rt.open()
    _LIVE[call.id] = {"rt": rt, "call_id": call.id, "lead_id": lead.id}
    save_call_state(db, rt, lead.id, agent.id, active=True)
    db.commit()
    bus.emit("call.started", {"call_id": call.id})
    return Ok(data={"call_id": call.id, "state": rt.sm.state, "agent": opening.agent_text})


@app.post("/v1/calls/{call_id}/turn")
def call_turn(call_id: str, body: TurnIn, db: Session = Depends(get_db)) -> Ok:
    live = _LIVE.get(call_id)
    if live:
        rt = live["rt"]
        lead_id = live["lead_id"]
    else:
        # Recover a call handled by another worker or from before a restart.
        rt = load_runtime(db, call_id)
        if not rt:
            raise HTTPException(404, "call_not_active")
        lead_id = rt.lead["id"]
        _LIVE[call_id] = {"rt": rt, "call_id": call_id, "lead_id": lead_id}
    turn = rt.handle(body.text)
    bus.emit("conversation.turn", {"call_id": call_id, "state": turn.state})

    # Save all details after every turn.
    lead = db.get(Lead, lead_id)
    persist_turn(db, lead, rt)
    save_call_state(db, rt, lead_id, "", active=not turn.ended)
    db.commit()

    resp = {"agent": turn.agent_text, "state": turn.state, "ended": turn.ended,
            "tool_calls": turn.tool_calls, "handoff": turn.handoff}
    if turn.ended:
        call = db.get(Call, call_id)
        persist_conversation(db, call, rt)
        ins = finalize_call(db, call, rt)
        deactivate_call_state(db, call_id)
        # Automatic follow-up is scheduled inside finalize_call.
        db.commit()
        _LIVE.pop(call_id, None)
        resp["insights_id"] = ins.id
        resp["next_action"] = ins.next_action
        bus.emit("call.ended", {"call_id": call_id})
    return Ok(data=resp)


@app.get("/v1/calls")
def list_calls(db: Session = Depends(get_db)) -> Ok:
    calls = db.scalars(select(Call)).all()
    return Ok(data=[{"id": c.id, "lead_id": c.lead_id, "status": c.status,
                     "outcome": c.outcome} for c in calls])


@app.get("/v1/calls/{call_id}")
def get_call(call_id: str, db: Session = Depends(get_db)) -> Ok:
    call = db.get(Call, call_id)
    if not call:
        raise HTTPException(404, "call_not_found")
    return Ok(data={"id": call.id, "lead_id": call.lead_id, "status": call.status,
                    "outcome": call.outcome})


@app.post("/v1/calls/{call_id}/transfer")
def transfer_call(call_id: str, db: Session = Depends(get_db)) -> Ok:
    live = _LIVE.get(call_id)
    if not live:
        raise HTTPException(404, "call_not_active")
    rt = live["rt"]
    from .agent_runtime.handoff import build_handoff
    ctx = build_handoff(rt.lead, rt.product, rt.memory, "")
    res = rt.tools.call("human.transfer", {"lead_id": rt.lead["id"], "context": ctx})
    return Ok(data={"transferred": res.get("ok", False), "context": ctx})


@app.post("/v1/calls/{call_id}/end")
def end_call(call_id: str, db: Session = Depends(get_db)) -> Ok:
    live = _LIVE.pop(call_id, None)
    call = db.get(Call, call_id)
    if not call:
        raise HTTPException(404, "call_not_found")
    if live:
        persist_conversation(db, call, live["rt"])
        finalize_call(db, call, live["rt"])
    else:
        call.status = "completed"
    db.commit()
    bus.emit("call.ended", {"call_id": call_id})
    return Ok(data={"id": call_id, "ended": True})


# ---- conversations -------------------------------------------------------
@app.get("/v1/conversations/{conversation_id}")
def get_conversation(conversation_id: str, db: Session = Depends(get_db)) -> Ok:
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(404, "conversation_not_found")
    return Ok(data={"id": conv.id, "state": conv.state, "lead_id": conv.lead_id})


@app.get("/v1/conversations/{conversation_id}/transcript")
def get_transcript(conversation_id: str, db: Session = Depends(get_db)) -> Ok:
    msgs = db.scalars(select(ConversationMessage)
                      .where(ConversationMessage.conversation_id == conversation_id)).all()
    return Ok(data=[{"role": m.role, "text": m.text, "state": m.state} for m in msgs])


@app.get("/v1/conversations/{conversation_id}/insights")
def get_insights(conversation_id: str, db: Session = Depends(get_db)) -> Ok:
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(404, "conversation_not_found")
    ins = db.scalar(select(CallInsight).where(CallInsight.call_id == conv.call_id))
    if not ins:
        return Ok(data={})
    return Ok(data={"summary": ins.summary, "sentiment": ins.sentiment,
                    "objections": ins.objections, "facts": ins.facts,
                    "next_action": ins.next_action})


# ---- followups & calendar ------------------------------------------------
@app.post("/v1/followups")
def create_followup(body: FollowupIn, db: Session = Depends(get_db)) -> Ok:
    from datetime import timedelta
    fu = Followup(org_id=app.state.seed["org_id"], lead_id=body.lead_id, reason=body.reason,
                  channel=body.channel,
                  due_at=datetime.utcnow() + timedelta(hours=body.due_in_hours))
    db.add(fu)
    db.commit()
    bus.emit("followup.created", {"followup_id": fu.id})
    return Ok(data={"id": fu.id, "due_at": fu.due_at.isoformat()})


@app.get("/v1/followups")
def list_followups(db: Session = Depends(get_db)) -> Ok:
    fus = db.scalars(select(Followup)).all()
    return Ok(data=[{"id": f.id, "lead_id": f.lead_id, "reason": f.reason,
                     "status": f.status, "due_at": f.due_at.isoformat()} for f in fus])


@app.patch("/v1/followups/{followup_id}")
def patch_followup(followup_id: str, db: Session = Depends(get_db)) -> Ok:
    fu = db.get(Followup, followup_id)
    if not fu:
        raise HTTPException(404, "followup_not_found")
    fu.status = "rescheduled"
    db.commit()
    return Ok(data={"id": followup_id})


@app.post("/v1/followups/{followup_id}/cancel")
def cancel_followup(followup_id: str, db: Session = Depends(get_db)) -> Ok:
    fu = db.get(Followup, followup_id)
    if not fu:
        raise HTTPException(404, "followup_not_found")
    fu.status = "cancelled"
    db.commit()
    return Ok(data={"id": followup_id, "status": "cancelled"})


@app.post("/v1/calendar/check")
def calendar_check(body: CalendarCheck) -> Ok:
    return Ok(data={"slots": ["tomorrow 5pm", "tomorrow 6pm", "sat 11am"]})


@app.post("/v1/calendar/book")
def calendar_book(body: CalendarBook, db: Session = Depends(get_db)) -> Ok:
    tools = ToolRegistry()
    res = tools.call("calendar.book", {"lead_id": body.lead_id, "slot": body.slot})
    bus.emit("appointment.booked", res.get("result", {}))
    return Ok(data=res.get("result"))


# ---- analytics -----------------------------------------------------------
@app.get("/v1/analytics/funnel")
def analytics_funnel(db: Session = Depends(get_db)) -> Ok:
    leads = db.scalars(select(Lead)).all()
    funnel: dict[str, int] = {}
    for l in leads:
        funnel[l.stage] = funnel.get(l.stage, 0) + 1
    return Ok(data={"total_leads": len(leads), "by_stage": funnel})


@app.get("/v1/analytics/agents")
def analytics_agents(db: Session = Depends(get_db)) -> Ok:
    calls = db.scalars(select(Call)).all()
    outcomes: dict[str, int] = {}
    for c in calls:
        outcomes[c.outcome or "open"] = outcomes.get(c.outcome or "open", 0) + 1
    return Ok(data={"total_calls": len(calls), "by_outcome": outcomes})


@app.get("/v1/analytics/campaigns/{campaign_id}")
def analytics_campaign(campaign_id: str, db: Session = Depends(get_db)) -> Ok:
    camp = db.get(Campaign, campaign_id)
    if not camp:
        raise HTTPException(404, "campaign_not_found")
    return Ok(data={"id": camp.id, "status": camp.status, "leads": len(camp.lead_ids or [])})


# ---- webhooks ------------------------------------------------------------
@app.post("/v1/webhooks/telephony")
def webhook_telephony(payload: dict) -> Ok:
    bus.emit("call.started", payload)
    return Ok(data={"received": True})


@app.post("/v1/webhooks/payment")
def webhook_payment(payload: dict) -> Ok:
    bus.emit("deal.created", payload)
    return Ok(data={"received": True})


@app.post("/v1/webhooks/calendar")
def webhook_calendar(payload: dict) -> Ok:
    bus.emit("appointment.booked", payload)
    return Ok(data={"received": True})


# ---- simulator -----------------------------------------------------------
@app.post("/v1/simulate")
def simulate(body: SimulateIn) -> Ok:
    return Ok(data=run_sim(body.prospect))


# ---- automatic follow-up scheduler --------------------------------------
@app.post("/v1/scheduler/tick")
def scheduler_tick() -> Ok:
    """Run any due follow-ups now (also runs automatically in the background)."""
    return Ok(data=run_due())


@app.get("/v1/leads/{lead_id}/facts")
def lead_facts(lead_id: str, db: Session = Depends(get_db)) -> Ok:
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "lead_not_found")
    return Ok(data={f.key: {"value": f.value, "confidence": f.confidence,
                            "source_call": f.source_call_id} for f in lead.facts})


@app.get("/v1/leads/{lead_id}/activities")
def lead_activities(lead_id: str, db: Session = Depends(get_db)) -> Ok:
    acts = db.scalars(select(Activity).where(Activity.lead_id == lead_id)).all()
    return Ok(data=[{"kind": a.kind, "body": a.body,
                     "at": a.created_at.isoformat()} for a in acts])


@app.post("/v1/voice/preview")
def voice_preview(payload: dict) -> Ok:
    """Synthesize a line with the configured TTS provider (real audio when keys set)."""
    tts = TTSProvider(voice=payload.get("voice", "nova"))
    out = tts.synthesize(payload.get("text", "Hello, this is a quick call."))
    out.pop("audio", None)  # don't ship raw bytes in JSON
    return Ok(data=out)


@app.post("/v1/voice/listen")
def voice_listen(payload: dict) -> Ok:
    """Transcribe speech with the configured STT provider (Deepgram when keys set)."""
    stt = STTProvider()
    out = stt.transcribe(words=payload.get("words"))
    return Ok(data=out)
