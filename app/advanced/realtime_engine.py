from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..providers.router import router
from ..realtime.session_manager import RealtimeSession


@dataclass
class LatencyBudget:
    # target per-stage budget in ms for a natural, full-duplex feel
    vad_ms: int = 20
    stt_partial_ms: int = 120
    plan_ms: int = 40
    llm_first_token_ms: int = 250
    tts_first_chunk_ms: int = 120

    def total(self) -> int:
        return (self.vad_ms + self.stt_partial_ms + self.plan_ms
                + self.llm_first_token_ms + self.tts_first_chunk_ms)


@dataclass
class RealtimeEngine:
    """Orchestrates the full-duplex loop: audio frames flow in continuously while
    the agent may be speaking; STT streams partials, the planner runs on endpoint,
    and TTS streams out with instant barge-in. Wraps RealtimeSession + the provider
    router and tracks a latency budget so regressions are visible."""

    call_id: str
    voice: str = "nova"
    budget: LatencyBudget = field(default_factory=LatencyBudget)
    session: RealtimeSession = field(default=None)  # type: ignore[assignment]
    metrics: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = RealtimeSession(call_id=self.call_id, voice=self.voice)
        self.providers = router.plan()

    def negotiate(self, offered_codecs: list[str]) -> str:
        return self.session.negotiate(offered_codecs)

    def push_frames(self, rms_frames: list[float]) -> list[dict]:
        """Feed a burst of mic frames; returns per-frame full-duplex decisions."""
        return [self.session.on_frame(r) for r in rms_frames]

    def turn(self, words: list[str], on_speak) -> dict:
        """One barge-in-safe exchange. `on_speak(text)->str` produces the reply
        (e.g. the agent runtime). Returns transcript + measured latency."""
        t0 = time.perf_counter()
        heard = self.session.hear(words, silence_ms=self.session.turn.silence_ms)
        transcript = heard if heard is not None else " ".join(words)
        reply = on_speak(transcript)
        chunks = self.session.say(reply)
        elapsed = int((time.perf_counter() - t0) * 1000)
        m = {"heard": transcript, "reply": reply, "chunks": len(chunks),
             "latency_ms": elapsed, "budget_ms": self.budget.total(),
             "within_budget": elapsed <= self.budget.total() * 4}  # generous local bound
        self.metrics.append(m)
        return m

    def stats(self) -> dict:
        if not self.metrics:
            return {"turns": 0}
        lat = [m["latency_ms"] for m in self.metrics]
        return {"turns": len(lat), "avg_latency_ms": sum(lat) // len(lat),
                "providers": self.providers, "codec": self.session.audio.codec}
