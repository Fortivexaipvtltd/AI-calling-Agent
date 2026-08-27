from __future__ import annotations

from dataclasses import dataclass, field

from ..providers.stt import STTProvider
from .audio import AudioPipeline
from .stt import StreamingSTT
from .tts import StreamingTTS
from .turn_detection import TurnDetector
from .vad import VAD


@dataclass
class RealtimeSession:
    call_id: str
    voice: str = "nova"
    vad: VAD = field(default_factory=VAD)
    turn: TurnDetector = field(default_factory=TurnDetector)
    stt: StreamingSTT = field(default_factory=StreamingSTT)
    asr: STTProvider = field(default_factory=STTProvider)
    audio: AudioPipeline = field(default_factory=AudioPipeline)
    tts: StreamingTTS = field(default=None)  # type: ignore[assignment]
    speaking: bool = False
    _far_rms: float = 0.0

    def __post_init__(self) -> None:
        if self.tts is None:
            self.tts = StreamingTTS(self.voice)

    def negotiate(self, offered_codecs: list[str]) -> str:
        return self.audio.set_codec(offered_codecs)

    def on_frame(self, near_rms: float) -> dict:
        """Full-duplex: clean the mic frame (AEC+NS) while we may be speaking,
        then decide speech. If the lead speaks over the agent -> barge-in."""
        stats = self.audio.process_frame(near_rms, far_rms=self._far_rms)
        if stats.is_speech and self.speaking:
            self.barge_in()
        return {"rms": round(stats.rms, 4), "speech": stats.is_speech,
                "echo_removed": stats.echo_removed, "codec": self.audio.codec}

    def barge_in(self) -> None:
        """Lead interrupts -> cancel TTS, return to listening."""
        self.tts.cancel()
        self.speaking = False
        self._far_rms = 0.0

    def listen(self, *, words: list[str] | None = None, audio: bytes | None = None,
               content_type: str = "audio/wav") -> dict:
        """Real listening: transcribe via the configured STT provider."""
        return self.asr.transcribe(words=words, audio=audio, content_type=content_type)

    def hear(self, words: list[str], silence_ms: int = 1000) -> str | None:
        """Feed lead audio words; return final transcript when the turn ends."""
        partial = ""
        for _partial in self.stt.stream(words):
            if self.speaking:
                self.barge_in()
        if self.turn.finished(silence_ms, partial):
            return self.stt.transcribe(words)
        return None

    def say(self, text: str) -> list[str]:
        self.speaking = True
        self._far_rms = 0.06  # agent audio present -> AEC reference is non-zero
        out = list(self.tts.stream(text))
        self.speaking = False
        self._far_rms = 0.0
        return out
