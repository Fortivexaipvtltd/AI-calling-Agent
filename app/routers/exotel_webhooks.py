from __future__ import annotations

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from ..config import settings
from ..telephony import exotel

router = APIRouter(prefix="/v1/telephony/exotel", tags=["exotel"])


def _xml(body: str) -> Response:
    return Response(content=body, media_type="application/xml")


async def _form(request: Request) -> dict:
    try:
        return {k: v for k, v in (await request.form()).items()}
    except Exception:
        try:
            from urllib.parse import parse_qs
            raw = (await request.body()).decode()
            return {k: v[0] for k, v in parse_qs(raw).items()}
        except Exception:
            return dict(request.query_params)


def _base_url(request: Request) -> str:
    return settings.public_base_url or str(request.base_url).rstrip("/")


@router.post("/answer")
@router.get("/answer")
async def answer(request: Request) -> Response:
    """Exotel connects the call here. Create/lookup the lead from caller number,
    open the agent, greet, and gather the caller's first utterance."""
    form = await _form(request)
    from_number = form.get("From", form.get("CallFrom", ""))
    from ..db import SessionLocal
    from ..models import Agent, Lead
    from ..service import build_runtime, save_call_state
    db = SessionLocal()
    try:
        from sqlalchemy import select
        lead = db.scalar(select(Lead).where(Lead.phone == from_number))
        if not lead:
            lead = Lead(org_id=settings.default_org_id, name="Exotel caller",
                        phone=from_number, source="inbound", status="new")
            db.add(lead)
            db.flush()
        agent = db.scalar(select(Agent))
        rt, call, _ = build_runtime(db, lead, agent)
        opened = rt.open()
        opening = getattr(opened, "agent_text", None) or (
            opened if isinstance(opened, str) else "Hello, thanks for calling.")
        save_call_state(db, rt, lead.id, agent.id if agent else "", active=True)
        db.commit()
        gather_url = f"{_base_url(request)}/v1/telephony/exotel/gather?call_id={call.id}"
        return _xml(exotel.answer_exoml(opening_line=opening, gather_url=gather_url))
    finally:
        db.close()


@router.post("/gather")
async def gather(request: Request) -> Response:
    """Each caller utterance (speech-to-text by Exotel) lands here; we run one
    agent turn and respond with the next ExoML (say + gather, or say + hangup)."""
    form = await _form(request)
    call_id = request.query_params.get("call_id", "") or form.get("call_id", "")
    speech = form.get("SpeechResult", form.get("digits", form.get("Digits", "")))
    from ..db import SessionLocal
    from ..models import Lead
    from ..service import load_runtime, persist_turn, save_call_state
    db = SessionLocal()
    try:
        rt = load_runtime(db, call_id)
        if not rt:
            return _xml(exotel.say_and_gather(
                text="Sorry, the session expired. We'll call you back shortly.",
                gather_url="", hangup=True))
        lead_id = getattr(rt, "lead", {}).get("id", "") if hasattr(rt, "lead") else ""
        turn = rt.handle(speech or "")
        lead = db.get(Lead, lead_id) if lead_id else None
        # Live actions (send brochure/book/etc.) mid-call.
        try:
            from ..agent_runtime import live_actions
            live_actions.run_detected(db, lead=lead, agent_text=turn.agent_text,
                                      lead_text=speech or "")
        except Exception:
            pass
        persist_turn(db, lead, rt)
        save_call_state(db, rt, lead_id, "", active=not turn.ended)
        db.commit()
        base = _base_url(request)
        gather_url = f"{base}/v1/telephony/exotel/gather?call_id={call_id}"
        return _xml(exotel.say_and_gather(text=turn.agent_text, gather_url=gather_url,
                                          hangup=bool(turn.ended)))
    finally:
        db.close()


@router.post("/status")
async def status(request: Request) -> dict:
    form = await _form(request)
    data = exotel.parse_status(form)
    return {"ok": True, "data": data}


@router.websocket("/voicebot/{call_id}")
async def voicebot(ws: WebSocket, call_id: str) -> None:
    """Exotel Voicebot streaming: bidirectional 8k PCM. Bridges the caller audio
    to STT -> agent -> TTS and streams speech back. Falls back gracefully when
    providers aren't configured (keeps the socket alive, echoes state)."""
    await ws.accept()
    from ..realtime.exotel_stream import ExotelStreamBridge
    bridge = ExotelStreamBridge(call_id)
    try:
        await bridge.run(ws)
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await ws.close()
        except Exception:
            pass
