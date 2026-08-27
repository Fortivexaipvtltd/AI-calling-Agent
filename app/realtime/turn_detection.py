from __future__ import annotations

from ..config import settings


class TurnDetector:
    """Detect when the lead finished a thought."""

    def __init__(self, silence_ms: int | None = None) -> None:
        self.silence_ms = silence_ms or settings.turn_silence_ms

    def finished(self, silence_elapsed_ms: int, partial_text: str) -> bool:
        text = partial_text.strip()
        if not text:
            return False
        if silence_elapsed_ms >= self.silence_ms:
            return True
        return text.endswith((".", "?", "!"))
