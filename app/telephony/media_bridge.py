from __future__ import annotations

import audioop
import base64
from dataclasses import dataclass, field

from ..providers.router import router
from ..realtime.audio import AudioPipeline


def mulaw_to_pcm16(mulaw_bytes: bytes) -> bytes:
    """Twilio Media Streams send 8kHz mu-law (G.711). Decode to linear PCM16."""
    return audioop.ulaw2lin(mulaw_bytes, 2)


def frame_rms(pcm16: bytes) -> float:
    """Normalised RMS (0..1) of a PCM16 frame, for VAD/energy gating."""
    if not pcm16:
        return 0.0
    return audioop.rms(pcm16, 2) / 32768.0


@dataclass
class MediaBridge:
    """Consumes Twilio Media Stream events for one call and turns buffered audio
    into transcripts via the configured STT provider. The transport (WebSocket)
    is separate, so this is fully unit-testable by feeding it event dicts.

    Events (Twilio):
      {"event":"start",  "start":{"callSid":...}}
      {"event":"media",  "media":{"payload":"<base64 mu-law>"}}
      {"event":"stop"}
    """

    call_id: str
    stt: object = field(default=None)
    audio: AudioPipeline = field(default_factory=AudioPipeline)
    _buf: bytearray = field(default_factory=bytearray)
    silence_frames: int = 0
    speaking: bool = False
    transcripts: list[str] = field(default_factory=list)
    speech_threshold: float = 0.02
    endpoint_silence_frames: int = 8   # ~ consecutive quiet frames => end of turn

    def __post_init__(self) -> None:
        if self.stt is None:
            self.stt = router.stt()

    def handle_event(self, event: dict) -> dict | None:
        kind = event.get("event")
        if kind == "start":
            return {"event": "start", "call_id": self.call_id}
        if kind == "media":
            return self._on_media(event.get("media", {}).get("payload", ""))
        if kind == "stop":
            return self._flush("stop")
        return None

    def _on_media(self, payload_b64: str) -> dict | None:
        if not payload_b64:
            return None
        pcm = mulaw_to_pcm16(base64.b64decode(payload_b64))
        stats = self.audio.process_frame(frame_rms(pcm))
        if stats.is_speech:
            self._buf += pcm
            self.speaking = True
            self.silence_frames = 0
            return None
        if self.speaking:
            self.silence_frames += 1
            if self.silence_frames >= self.endpoint_silence_frames:
                return self._flush("endpoint")
        return None

    def _flush(self, reason: str) -> dict | None:
        if not self._buf:
            self.speaking = False
            return None
        audio = bytes(self._buf)
        self._buf = bytearray()
        self.speaking = False
        self.silence_frames = 0
        result = self.stt.transcribe(audio=audio, content_type="audio/l16;rate=8000")
        text = (result or {}).get("transcript", "")
        if text:
            self.transcripts.append(text)
        return {"event": "transcript", "reason": reason, "text": text,
                "provider": (result or {}).get("provider", "")}
