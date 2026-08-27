from __future__ import annotations

import threading
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from ..providers.tts import TTSProvider
from .prosody import ProsodyEngine, split_clauses


def clause_accumulator(token_stream: Iterable[str]) -> Iterator[str]:
    """Consume LLM tokens and emit complete clauses as soon as a boundary is
    seen. This is what lets synthesis start before the full reply is generated
    — the single biggest lever on perceived latency."""
    buf = ""
    enders = (".", "!", "?", ",", ";", ":")
    for tok in token_stream:
        buf += (tok if tok.startswith(" ") or not buf else " " + tok)
        if buf.strip().endswith(enders) or len(buf) > 90:
            for clause in split_clauses(buf):
                yield clause
            buf = ""
    for clause in split_clauses(buf):
        if clause:
            yield clause


@dataclass
class SpeakResult:
    clauses: list[str] = field(default_factory=list)
    audio_chunks: int = 0
    time_to_first_audio_ms: float = 0.0
    total_ms: float = 0.0
    barged_in: bool = False


class StreamingVoice:
    """Full-duplex speak pipeline. Given a token stream (or full text), it emits
    audio clause-by-clause with prosody applied, tracks time-to-first-audio, and
    can be interrupted instantly (barge-in) between/within clauses."""

    def __init__(self, tts: TTSProvider | None = None,
                 prosody: ProsodyEngine | None = None) -> None:
        self.tts = tts or TTSProvider()
        self.prosody = prosody or ProsodyEngine()
        self._cancel = threading.Event()

    def cancel(self) -> None:
        """Barge-in: stop speaking immediately."""
        self._cancel.set()

    def _reset(self) -> None:
        self._cancel.clear()

    def speak_stream(self, token_stream: Iterable[str], *, intent: str = "",
                     on_audio=None) -> SpeakResult:
        """Speak from a live token stream. Returns metrics including TTFA."""
        self._reset()
        res = SpeakResult()
        start = time.perf_counter()
        first_audio_at = None
        for clause in clause_accumulator(token_stream):
            if self._cancel.is_set():
                res.barged_in = True
                break
            ssml = self.prosody.to_ssml(clause, intent=intent)
            for chunk in self.tts.synthesize_stream(clause, ssml=ssml):
                if self._cancel.is_set():
                    res.barged_in = True
                    break
                if first_audio_at is None:
                    first_audio_at = time.perf_counter()
                res.audio_chunks += 1
                if on_audio:
                    on_audio(chunk)
            res.clauses.append(clause)
            if res.barged_in:
                break
        res.total_ms = (time.perf_counter() - start) * 1000
        res.time_to_first_audio_ms = ((first_audio_at - start) * 1000
                                      if first_audio_at else 0.0)
        return res

    def speak_text(self, text: str, *, intent: str = "", on_audio=None) -> SpeakResult:
        """Convenience: speak a complete line (still streamed clause-by-clause)."""
        return self.speak_stream(iter(text.split()), intent=intent, on_audio=on_audio)
