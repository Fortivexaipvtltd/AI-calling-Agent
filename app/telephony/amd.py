from __future__ import annotations

from ..config import settings

# Phrases/patterns typical of machine greetings.
_MACHINE_CUES = (
    "leave a message", "after the tone", "after the beep", "not available",
    "voicemail", "recorded", "please leave", "reached the voicemail",
    "unavailable", "record your message",
)
_BEEP_CUES = ("beep", "tone")


class AMDResult:
    def __init__(self, label: str, confidence: float, reason: str) -> None:
        self.label = label            # human | machine | unknown
        self.confidence = confidence
        self.reason = reason

    def __repr__(self) -> str:  # pragma: no cover
        return f"AMDResult({self.label}, {self.confidence:.2f}, {self.reason})"

    def as_dict(self) -> dict:
        return {"label": self.label, "confidence": self.confidence, "reason": self.reason}


class AnsweringMachineDetector:
    """Classifies the answering party from the opening audio/transcript.

    Signal-based heuristics (greeting length, beep, machine phrases) locally;
    real providers (Twilio AMD, Deepgram) drop in behind the same interface.
    """

    def detect(self, *, opening_transcript: str = "",
               greeting_ms: int = 0, beep_detected: bool = False) -> AMDResult:
        if not settings.amd_enabled:
            return AMDResult("unknown", 0.0, "amd_disabled")
        t = (opening_transcript or "").lower()
        if beep_detected or any(c in t for c in _BEEP_CUES):
            return AMDResult("machine", 0.95, "beep")
        if any(c in t for c in _MACHINE_CUES):
            return AMDResult("machine", 0.9, "machine_phrase")
        # Long uninterrupted greeting => likely a recording.
        if greeting_ms >= 3500:
            return AMDResult("machine", 0.7, "long_greeting")
        if t:
            return AMDResult("human", 0.8, "short_live_greeting")
        return AMDResult("unknown", 0.3, "insufficient_signal")


class VoicemailService:
    """Detects voicemail and, when configured, drops a pre-recorded/synthesized
    message instead of talking over the machine."""

    def __init__(self) -> None:
        self.detector = AnsweringMachineDetector()
        self.drops: list[dict] = []

    def on_answer(self, *, opening_transcript: str = "", greeting_ms: int = 0,
                  beep_detected: bool = False) -> AMDResult:
        return self.detector.detect(opening_transcript=opening_transcript,
                                    greeting_ms=greeting_ms, beep_detected=beep_detected)

    def drop_message(self, call_id: str, message: str) -> dict:
        rec = {"call_id": call_id, "message": message, "status": "left_voicemail"}
        self.drops.append(rec)
        return rec


voicemail = VoicemailService()
