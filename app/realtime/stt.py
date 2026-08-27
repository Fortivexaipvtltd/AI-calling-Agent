from __future__ import annotations

from collections.abc import Iterator


class StreamingSTT:
    """Streaming speech recognition. Local stub yields progressive partials."""

    def stream(self, words: list[str]) -> Iterator[str]:
        buf: list[str] = []
        for w in words:
            buf.append(w)
            yield " ".join(buf)

    def transcribe(self, words: list[str]) -> str:
        return " ".join(words).strip()
