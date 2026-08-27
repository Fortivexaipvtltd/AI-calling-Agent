from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from ..providers.tts import TTSProvider
from ..telephony.media_bridge import MediaBridge, frame_rms, mulaw_to_pcm16
from .prosody import ProsodyEngine

# on_turn(text) -> (agent_text, intent, ended). Runs the LLM/agent runtime.
TurnFn = Callable[[str], tuple[str, str, bool]]
# send(event_dict) -> awaitable. Writes a Twilio Media Stream frame back.
SendFn = Callable[[dict], Awaitable[None]]

TWILIO_FRAME_BYTES = 160        # 20 ms of 8 kHz mu-law
SPEECH_RMS = 0.05               # inbound energy that counts as the caller talking


@dataclass
class PipelineMetrics:
    transcripts: int = 0
    agent_turns: int = 0
    frames_sent: int = 0
    barge_ins: int = 0


@dataclass
class RealtimeCallPipeline:
    """Full-duplex bridge for one call:

        Twilio Media Stream (in)  ->  Deepgram STT (stream)  ->  LLM/agent
              ^                                                       |
              |                                                       v
        Twilio Media Stream (out) <-  ElevenLabs mu-law (stream) <- prosody

    Inbound mu-law frames are transcribed (Deepgram streaming when a key is set,
    else local endpointing). A final transcript drives the agent; the reply is
    streamed through ElevenLabs as mu-law and written straight back over the same
    socket in 20 ms frames. If the caller talks while the agent is speaking, we
    barge in: cancel synthesis and send Twilio a `clear` to flush queued audio.
    """

    call_id: str
    send: SendFn
    on_turn: TurnFn
    tts: TTSProvider = field(default=None)          # type: ignore[assignment]
    stt_stream: object = None                       # optional DeepgramStream
    prosody: ProsodyEngine = field(default_factory=ProsodyEngine)
    stream_sid: str = ""
    speaking: bool = False
    metrics: PipelineMetrics = field(default_factory=PipelineMetrics)
    _bridge: MediaBridge = field(default=None)      # type: ignore[assignment]
    _interrupt: bool = False
    _speak_task: object = None

    def __post_init__(self) -> None:
        if self.tts is None:
            self.tts = TTSProvider()
        if self._bridge is None:
            # Local endpointer used when no streaming STT is wired.
            self._bridge = MediaBridge(call_id=self.call_id,
                                       stt=getattr(self, "_stt", None))

    # ---- inbound (Twilio -> us) -----------------------------------------
    async def handle_event(self, event: dict) -> None:
        kind = event.get("event")
        if kind == "start":
            self.stream_sid = event.get("start", {}).get("streamSid", self.stream_sid) \
                or event.get("streamSid", self.stream_sid)
            if self.stt_stream is not None:
                await self.stt_stream.connect(encoding="mulaw", sample_rate=8000)
            return
        if kind == "media":
            await self._on_media(event.get("media", {}).get("payload", ""))
            return
        if kind == "stop":
            await self._flush_and_close()

    async def _on_media(self, payload_b64: str) -> None:
        if not payload_b64:
            return
        raw = base64.b64decode(payload_b64)

        # Barge-in: caller speaks over the agent -> stop talking immediately.
        if self.speaking and frame_rms(mulaw_to_pcm16(raw)) >= SPEECH_RMS:
            await self.barge_in()

        if self.stt_stream is not None:
            # Streaming path: forward audio; transcripts arrive via the DG loop.
            await self.stt_stream.send(raw)
            return

        # Local path: buffer + endpoint, transcribe on end of utterance.
        result = self._bridge.handle_event(
            {"event": "media", "media": {"payload": payload_b64}})
        if result and result.get("event") == "transcript" and result.get("text"):
            await self.on_transcript(result["text"])

    async def _flush_and_close(self) -> None:
        if self.stt_stream is not None:
            await self.stt_stream.finish()
            return
        result = self._bridge._flush("stop")
        if result and result.get("text"):
            await self.on_transcript(result["text"])

    # ---- transcript -> agent -> speech ----------------------------------
    async def on_transcript(self, text: str) -> None:
        """Called with a FINAL transcript (from Deepgram or the local endpointer)."""
        self.metrics.transcripts += 1
        agent_text, intent, ended = self.on_turn(text)
        self.metrics.agent_turns += 1
        if agent_text:
            # Speak as a background task so we keep receiving inbound audio
            # (that's what makes barge-in possible).
            self._speak_task = asyncio.ensure_future(self._speak(agent_text, intent))
            if ended:
                await self._speak_task

    async def _speak(self, text: str, intent: str = "") -> None:
        self.speaking = True
        self._interrupt = False
        ssml = self.prosody.to_ssml(text, intent=intent)
        buf = b""
        try:
            for chunk in self.tts.stream_ulaw(text, ssml=ssml):
                if self._interrupt:
                    break
                buf += chunk
                while len(buf) >= TWILIO_FRAME_BYTES:
                    if self._interrupt:
                        break
                    frame, buf = buf[:TWILIO_FRAME_BYTES], buf[TWILIO_FRAME_BYTES:]
                    await self._send_media(frame)
                    await asyncio.sleep(0)          # yield so inbound can interrupt
            if buf and not self._interrupt:
                await self._send_media(buf)
        finally:
            self.speaking = False

    async def _send_media(self, ulaw_frame: bytes) -> None:
        await self.send({"event": "media", "streamSid": self.stream_sid,
                         "media": {"payload": base64.b64encode(ulaw_frame).decode()}})
        self.metrics.frames_sent += 1

    async def barge_in(self) -> None:
        self._interrupt = True
        self.speaking = False
        self.metrics.barge_ins += 1
        task = self._speak_task
        if task is not None and not task.done():
            task.cancel()
        # Tell Twilio to drop any audio it has buffered for playback.
        await self.send({"event": "clear", "streamSid": self.stream_sid})

    async def drain(self) -> None:
        """Await any in-flight speech (used at end of call / in tests)."""
        task = self._speak_task
        if task is not None and not task.done():
            try:
                await task
            except asyncio.CancelledError:
                pass


def make_deepgram_stream(on_final: Callable[[str], Awaitable[None]]):
    """Build a DeepgramStream whose final transcripts drive `on_final`. Returns
    None if streaming isn't available (no key / `websockets` not installed), so
    the pipeline transparently uses local endpointing instead."""
    from ..config import settings
    if not settings.stt_api_key:
        return None
    try:
        from ..providers.deepgram_stream import DeepgramStream
    except Exception:
        return None

    loop = asyncio.get_event_loop()

    def _cb(evt: dict) -> None:
        if evt.get("is_final") and evt.get("text"):
            asyncio.run_coroutine_threadsafe(on_final(evt["text"]), loop)

    return DeepgramStream(on_transcript=_cb)
