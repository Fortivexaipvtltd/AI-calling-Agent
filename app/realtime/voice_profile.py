from __future__ import annotations

"""Single place to tune how human the voice sounds.

Edit numbers here — no other code changes needed. Every value is applied live by
the prosody engine and the ElevenLabs provider. Pick a preset with
VOICE_PROFILE=warm_consultative (or set it in .env), then fine-tune by ear using
`python -m scripts.voice_preview` once your ElevenLabs key is set.
"""

import json
from dataclasses import dataclass, field

from ..config import _env


@dataclass
class IntentStyle:
    rate: str            # speaking speed, e.g. "96%"
    pitch: str           # e.g. "-1st", "+1st"
    sentence_pause_ms: int
    opener: str = ""     # natural lead-in, "" for none


@dataclass
class ElevenSettings:
    model_id: str = "eleven_turbo_v2_5"
    stability: float = 0.45          # lower = more expressive, higher = steadier
    similarity_boost: float = 0.8
    style: float = 0.35              # 0..1 expressiveness
    use_speaker_boost: bool = True
    optimize_streaming_latency: int = 3   # 0..4, higher = faster first byte
    output_format: str = "mp3_44100_128"


@dataclass
class VoiceProfile:
    name: str
    # tuning that makes speech feel human
    comma_pause_ms: int = 140
    opener_pause_ms: int = 180
    eleven: ElevenSettings = field(default_factory=ElevenSettings)
    styles: dict[str, IntentStyle] = field(default_factory=dict)
    emphasis_words: set[str] = field(default_factory=set)

    def style(self, key: str) -> IntentStyle:
        return self.styles.get(key, self.styles["default"])


_VALUE_WORDS = {
    "free", "guarantee", "guaranteed", "today", "now", "only", "exactly",
    "results", "outcome", "job", "career", "save", "proven", "personally",
    "limited", "best", "fastest",
}


def _warm_consultative() -> VoiceProfile:
    """Friendly, unhurried, trustworthy — good default for sales calls."""
    return VoiceProfile(
        name="warm_consultative",
        comma_pause_ms=150, opener_pause_ms=200,
        eleven=ElevenSettings(stability=0.42, similarity_boost=0.82, style=0.38),
        emphasis_words=set(_VALUE_WORDS),
        styles={
            "default":   IntentStyle("99%", "0st", 320),
            "empathy":   IntentStyle("92%", "-1st", 440, opener="I hear you —"),
            "objection": IntentStyle("94%", "0st", 380, opener="That's fair —"),
            "confirm":   IntentStyle("103%", "+1st", 260, opener="Perfect —"),
            "discover":  IntentStyle("98%", "0st", 320, opener="Got it —"),
        },
    )


def _brisk_closer() -> VoiceProfile:
    """Higher energy, quicker, for warm leads ready to move."""
    return VoiceProfile(
        name="brisk_closer",
        comma_pause_ms=110, opener_pause_ms=140,
        eleven=ElevenSettings(stability=0.38, similarity_boost=0.78, style=0.5,
                              optimize_streaming_latency=4),
        emphasis_words=set(_VALUE_WORDS),
        styles={
            "default":   IntentStyle("104%", "+1st", 240),
            "empathy":   IntentStyle("98%", "0st", 340, opener="Totally get it —"),
            "objection": IntentStyle("100%", "0st", 300, opener="Quick thought —"),
            "confirm":   IntentStyle("108%", "+2st", 200, opener="Love it —"),
            "discover":  IntentStyle("102%", "0st", 260, opener="Nice —"),
        },
    )


def _calm_support() -> VoiceProfile:
    """Slow, gentle, reassuring — for anxious or confused callers."""
    return VoiceProfile(
        name="calm_support",
        comma_pause_ms=180, opener_pause_ms=240,
        eleven=ElevenSettings(stability=0.55, similarity_boost=0.85, style=0.25),
        emphasis_words={"safe", "support", "here", "help", "guarantee", "personally"},
        styles={
            "default":   IntentStyle("94%", "-1st", 380),
            "empathy":   IntentStyle("88%", "-2st", 520, opener="Take your time —"),
            "objection": IntentStyle("90%", "-1st", 440, opener="I understand —"),
            "confirm":   IntentStyle("96%", "0st", 320, opener="Wonderful —"),
            "discover":  IntentStyle("92%", "-1st", 380, opener="Sure —"),
        },
    )


PRESETS = {
    "warm_consultative": _warm_consultative,
    "brisk_closer": _brisk_closer,
    "calm_support": _calm_support,
}


def load_profile() -> VoiceProfile:
    name = _env("VOICE_PROFILE", "warm_consultative")
    profile = PRESETS.get(name, _warm_consultative)()
    # Optional JSON overrides for quick ear-tuning without code edits:
    #   VOICE_OVERRIDES='{"comma_pause_ms":120,"eleven":{"style":0.5}}'
    raw = _env("VOICE_OVERRIDES", "")
    if raw:
        try:
            _apply_overrides(profile, json.loads(raw))
        except Exception:
            pass
    return profile


def _apply_overrides(profile: VoiceProfile, data: dict) -> None:
    for key, val in data.items():
        if key == "eleven" and isinstance(val, dict):
            for ek, ev in val.items():
                if hasattr(profile.eleven, ek):
                    setattr(profile.eleven, ek, ev)
        elif key == "styles" and isinstance(val, dict):
            for sk, sv in val.items():
                if sk in profile.styles and isinstance(sv, dict):
                    for field_name, field_val in sv.items():
                        if hasattr(profile.styles[sk], field_name):
                            setattr(profile.styles[sk], field_name, field_val)
        elif hasattr(profile, key):
            setattr(profile, key, val)


profile = load_profile()
