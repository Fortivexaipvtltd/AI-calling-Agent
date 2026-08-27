from __future__ import annotations

from dataclasses import dataclass

from ..config import settings

# Utterance endings that signal the speaker is NOT done yet -> wait longer.
_TRAILING_INCOMPLETE = (
    "and", "but", "so", "because", "if", "or", "the", "a", "to", "i", "my",
    "we", "you", "it's", "that", "when", "with", "for", "um", "uh", "like",
    "could", "would", "should", "can", "will", "might", "maybe", "just",
    "was", "is", "are", "want", "need", "gonna", "trying", "thinking",
)
# Endings that signal a complete thought / handoff of the turn -> respond sooner.
_COMPLETE_ENDINGS = (".", "?", "!")


@dataclass
class TurnDecision:
    should_respond: bool
    wait_ms: int
    reason: str


class TurnTakingPolicy:
    """Decides when the agent should start talking, so it feels like a person:
    - a clearly finished sentence -> respond after a short, natural gap,
    - a trailing conjunction/hesitation -> wait noticeably longer (don't cut in),
    - a barely-started fragment -> keep listening.
    Silence thresholds adapt to how complete the utterance sounds."""

    def __init__(self, base_silence_ms: int | None = None) -> None:
        self.base = base_silence_ms or settings.turn_silence_ms
        self.short = max(180, int(self.base * 0.6))   # complete thought
        self.long = int(self.base * 1.8)              # likely mid-thought

    def _looks_complete(self, text: str) -> bool:
        t = text.strip().lower()
        if not t:
            return False
        if t.endswith(_COMPLETE_ENDINGS):
            return True
        last = t.split()[-1]
        if last in _TRAILING_INCOMPLETE:
            return False
        # A reasonably long clause with no trailing conjunction reads as complete.
        return len(t.split()) >= 4

    def required_silence_ms(self, partial_text: str) -> int:
        t = partial_text.strip().lower()
        if not t:
            return self.long
        if t.endswith(_COMPLETE_ENDINGS):
            return self.short
        if t.split()[-1] in _TRAILING_INCOMPLETE:
            return self.long
        return self.base

    def decide(self, *, partial_text: str, silence_ms: int,
               agent_speaking: bool) -> TurnDecision:
        # If the human speaks while the agent talks, that's barge-in (handled
        # elsewhere); here we only decide when to START responding.
        if agent_speaking:
            return TurnDecision(False, 0, "agent_speaking")
        needed = self.required_silence_ms(partial_text)
        if not partial_text.strip():
            return TurnDecision(False, needed, "no_speech_yet")
        if silence_ms >= needed and self._looks_complete(partial_text):
            return TurnDecision(True, 0, "complete_and_silent")
        if silence_ms >= self.long:
            # They paused long even mid-thought -> gently take the turn.
            return TurnDecision(True, 0, "long_pause")
        return TurnDecision(False, needed - silence_ms, "still_listening")


policy = TurnTakingPolicy()
