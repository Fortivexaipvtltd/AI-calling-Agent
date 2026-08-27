from __future__ import annotations

from ..config import settings


class ConversationPolicy:
    """Natural conversation rules: one question at a time, short responses,
    react to what was actually said."""

    def enforce_one_question(self, text: str) -> str:
        if text.count("?") <= 1:
            return text
        head, _, _ = text.partition("?")
        return (head + "?").strip()

    def shorten(self, text: str) -> str:
        limit = settings.max_response_chars
        if len(text) <= limit:
            return text
        clipped = text[:limit].rsplit(" ", 1)[0]
        return clipped.rstrip(",;") + "."

    def apply(self, text: str) -> str:
        return self.shorten(self.enforce_one_question(text.strip()))
