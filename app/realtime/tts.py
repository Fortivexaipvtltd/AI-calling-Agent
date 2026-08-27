from __future__ import annotations

from collections.abc import Iterator

from .prosody import ProsodyEngine, split_clauses


class StreamingTTS:
    """Streaming speech synthesis. Streams clause-by-clause (not word-by-word) so
    barge-in stops at a natural boundary, and applies prosody for human pacing."""

    def __init__(self, voice: str = "nova") -> None:
        self.voice = voice
        self._cancelled = False
        self.prosody = ProsodyEngine()

    def cancel(self) -> None:
        self._cancelled = True

    def stream(self, text: str, *, intent: str = "") -> Iterator[str]:
        self._cancelled = False
        for clause in split_clauses(self.prosody.plain(text)):
            if self._cancelled:
                return
            yield clause

    def ssml(self, text: str, *, intent: str = "") -> str:
        return self.prosody.to_ssml(text, intent=intent)
