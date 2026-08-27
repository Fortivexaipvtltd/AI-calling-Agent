from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..observability.logging import log
from ..realtime.pipeline import RealtimeCallPipeline, make_deepgram_stream
from ..security.webhooks import verify_twilio
from ..telephony.twilio_voice import answer_twiml, parse_status, say_twiml

# These endpoints are called by Twilio, which cannot present our API key, so they
# are NOT behind bearer auth. They are authenticated by Twilio's request
# signature instead (HMAC over the exact URL + params with the auth token).
router = APIRouter(prefix="/v1/telephony/twilio", tags=["twilio"])


async def _verify(request: Request) -> dict:
    form = dict((await request.form()).items())
    if settings.validate_twilio_signature and settings.twilio_auth_token:
        url = str(request.url)
        sig = request.headers.get("X-Twilio-Signature", "")
        if not verify_twilio(url, form, sig):
            raise HTTPException(status_code=403, detail="invalid_twilio_signature")
    return form


def _twiml(xml: str) -> Response:
    return Response(content=xml, media_type="application/xml")


@router.post("/answer/{call_id}")
async def answer(call_id: str, request: Request, db: Session = Depends(get_db)) -> Response:
    await _verify(request)
    # Fetch the opening line from the live/durable call state if present.
    opening = "Hello, thanks for taking the call."
    try:
        from ..service import load_runtime
        rt = load_runtime(db, call_id)
        if rt and rt.turns:
            opening = rt.turns[0].agent_text or opening
    except Exception:
        pass
    return _twiml(answer_twiml(opening_line=opening, call_id=call_id))


@router.post("/gather/{call_id}")
async def gather(call_id: str, request: Request, db: Session = Depends(get_db)) -> Response:
    """Fallback (non-streaming) path: Twilio posts recognised speech here; we run
    one turn and answer with more TwiML."""
    form = await _verify(request)
    speech = form.get("SpeechResult", "")
    from ..service import load_runtime, save_call_state
    rt = load_runtime(db, call_id)
    if not rt:
        return _twiml(say_twiml("Sorry, this call has ended.", hangup=True))
    turn = rt.handle(speech)
    save_call_state(db, rt, rt.lead["id"], "", active=not turn.ended)
    db.commit()
    if turn.ended:
        return _twiml(say_twiml(turn.agent_text, hangup=True))
    return _twiml(answer_twiml(opening_line=turn.agent_text, call_id=call_id))


@router.post("/status")
async def status(request: Request) -> dict:
    form = await _verify(request)
    parsed = parse_status(form)
    log.info("twilio_status", extra={"path": "/v1/telephony/twilio/status"})
    # AMD result: if a machine answered, downstream can drop a voicemail.
    return {"ok": True, "data": parsed}


@router.post("/recording")
async def recording(request: Request) -> dict:
    form = await _verify(request)
    return {"ok": True, "data": {"recording_sid": form.get("RecordingSid", ""),
                                 "url": form.get("RecordingUrl", ""),
                                 "duration_s": int(form.get("RecordingDuration", "0") or 0)}}


@router.websocket("/media/{call_id}")
async def media(websocket: WebSocket, call_id: str) -> None:
    """Twilio Media Streams **bidirectional** bridge.

    Pipeline: Twilio (in) -> Deepgram STT -> LLM/agent runtime -> ElevenLabs
    (mu-law) -> Twilio (out), with barge-in. Inbound audio and outbound speech
    run concurrently on the same socket, so the caller can interrupt the agent.
    """
    await websocket.accept()

    async def send(frame: dict) -> None:
        await websocket.send_json(frame)

    def on_turn(text: str) -> tuple[str, str, bool]:
        """Advance the durable agent runtime by one turn (multi-worker safe)."""
        from ..db import SessionLocal
        from ..service import load_runtime, save_call_state
        db = SessionLocal()
        try:
            rt = load_runtime(db, call_id)
            if not rt:
                return "", "", True
            turn = rt.handle(text)
            save_call_state(db, rt, rt.lead["id"], "", active=not turn.ended)
            db.commit()
            intent = "confirm" if turn.ended else ("objection" if turn.handoff else "")
            return turn.agent_text, intent, turn.ended
        finally:
            db.close()

    pipeline = RealtimeCallPipeline(call_id=call_id, send=send, on_turn=on_turn)
    # Wire Deepgram streaming if configured; otherwise local endpointing is used.
    pipeline.stt_stream = make_deepgram_stream(pipeline.on_transcript)

    try:
        while True:
            event = await websocket.receive_json()
            await pipeline.handle_event(event)
            if event.get("event") == "stop":
                break
    except WebSocketDisconnect:
        pass
    finally:
        await pipeline.drain()
