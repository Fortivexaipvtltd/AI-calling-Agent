from __future__ import annotations

import asyncio
import base64
import json

# Bridges Exotel's Voicebot WebSocket to our agent. Exotel streams base64 PCM
# (8kHz, 16-bit, mono) in JSON frames: {"event":"media","media":{"payload":...}}
# and control events (start/stop/mark). We accumulate caller audio, transcribe on
# silence, run one agent turn, synthesize, and stream audio back in the same
# frame format. When STT/TTS providers aren't configured we degrade to a
# text-only exchange over the same socket so the pipeline stays testable.

_SILENCE_MS = 700
_FRAME_MS = 20


class ExotelStreamBridge:
    def __init__(self, call_id: str) -> None:
        self.call_id = call_id
        self.rt = None
        self.lead_id = ""
        self._buf = bytearray()
        self._silent_ms = 0
        self._speaking = False

    def _load(self) -> bool:
        from ..db import SessionLocal
        from ..service import load_runtime
        db = SessionLocal()
        try:
            rt = load_runtime(db, self.call_id)
            if not rt:
                return False
            self.rt = rt
            self.lead_id = rt.lead.get("id", "")
            return True
        finally:
            db.close()

    async def run(self, ws) -> None:
        if not self._load():
            await ws.send_text(json.dumps({"event": "error", "reason": "no_session"}))
            await ws.close()
            return
        # Greet immediately.
        await self._speak(ws, self.rt.transcript()[-1]["text"] if self.rt.transcript()
                          else "Hello!")
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            ev = msg.get("event")
            if ev == "media":
                await self._on_media(ws, msg)
            elif ev in ("stop", "disconnect"):
                break
            elif ev == "clear":
                self._buf.clear()

    async def _on_media(self, ws, msg) -> None:
        payload = (msg.get("media") or {}).get("payload", "")
        if not payload:
            return
        try:
            chunk = base64.b64decode(payload)
        except Exception:
            return
        self._buf.extend(chunk)
        # crude VAD: track silence by RMS of the frame
        if _rms(chunk) < 500:
            self._silent_ms += _FRAME_MS
        else:
            self._silent_ms = 0
            self._speaking = True
        if self._speaking and self._silent_ms >= _SILENCE_MS and self._buf:
            await self._flush_turn(ws)

    async def _flush_turn(self, ws) -> None:
        audio = bytes(self._buf)
        self._buf.clear()
        self._silent_ms = 0
        self._speaking = False
        text = self._transcribe(audio)
        if not text:
            return
        turn = self.rt.handle(text)
        self._persist(turn)
        await self._speak(ws, turn.agent_text)
        if turn.ended:
            await ws.send_text(json.dumps({"event": "stop"}))

    def _transcribe(self, audio: bytes) -> str:
        try:
            from ..providers.stt import stt
            r = stt.transcribe(audio=audio, content_type="audio/l16", language="en")
            return r.get("transcript", "")
        except Exception:
            return ""

    async def _speak(self, ws, text: str) -> None:
        if not text:
            return
        pcm = b""
        try:
            from ..providers.tts import tts
            pcm = tts.synthesize(text) or b""
        except Exception:
            pcm = b""
        if pcm:
            # stream back in 20ms frames
            step = int(8000 * 2 * _FRAME_MS / 1000)
            for i in range(0, len(pcm), step):
                frame = pcm[i:i + step]
                await ws.send_text(json.dumps({
                    "event": "media",
                    "media": {"payload": base64.b64encode(frame).decode()}}))
                await asyncio.sleep(_FRAME_MS / 1000)
        else:
            # text-only degrade (keeps socket + tests working without TTS)
            await ws.send_text(json.dumps({"event": "agent_text", "text": text}))

    def _persist(self, turn) -> None:
        from ..db import SessionLocal
        from ..models import Lead
        from ..service import persist_turn, save_call_state
        db = SessionLocal()
        try:
            lead = db.get(Lead, self.lead_id)
            persist_turn(db, lead, self.rt)
            save_call_state(db, self.rt, self.lead_id, "", active=not turn.ended)
            db.commit()
        finally:
            db.close()


def _rms(chunk: bytes) -> float:
    if len(chunk) < 2:
        return 0.0
    import struct
    n = len(chunk) // 2
    vals = struct.unpack(f"<{n}h", chunk[:n * 2])
    return (sum(v * v for v in vals) / n) ** 0.5 if n else 0.0
