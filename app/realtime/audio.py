from __future__ import annotations

from dataclasses import dataclass

from ..config import settings

# Codecs the engine can negotiate, with sample rates.
CODECS = {
    "opus": {"clock": 48000, "channels": 2, "kind": "wideband"},
    "pcmu": {"clock": 8000, "channels": 1, "kind": "narrowband"},  # G.711 µ-law
    "pcma": {"clock": 8000, "channels": 1, "kind": "narrowband"},  # G.711 A-law
    "g722": {"clock": 16000, "channels": 1, "kind": "wideband"},
}


def negotiate_codec(offered: list[str]) -> str:
    """Pick the best mutually supported codec (prefer wideband)."""
    ranked = ["opus", "g722", "pcma", "pcmu"]
    for c in ranked:
        if c in offered and c in CODECS:
            return c
    return settings.default_codec


@dataclass
class FrameStats:
    rms: float
    is_speech: bool
    suppressed_db: float
    echo_removed: bool


class NoiseSuppressor:
    """Spectral-gate style suppressor (level model locally; RNNoise/DTLN drop in)."""

    def __init__(self, floor_rms: float = 0.015) -> None:
        self.enabled = settings.noise_suppression
        self.floor = floor_rms

    def process(self, rms: float) -> tuple[float, float]:
        if not self.enabled or rms <= 0:
            return rms, 0.0
        if rms < self.floor:                 # below gate => attenuate as noise
            return rms * 0.1, 20.0
        return rms, 6.0                      # gentle broadband reduction on speech


class EchoCanceller:
    """Acoustic echo cancellation. Subtracts a scaled far-end (agent TTS) estimate
    from the near-end (lead mic) so the agent doesn't hear itself and self-barge."""

    def __init__(self) -> None:
        self.enabled = settings.echo_cancellation

    def process(self, near_rms: float, far_rms: float) -> tuple[float, bool]:
        if not self.enabled or far_rms <= 0:
            return near_rms, False
        cleaned = max(0.0, near_rms - 0.85 * far_rms)
        return cleaned, cleaned < near_rms


class AudioPipeline:
    """AEC -> NS -> VAD-ready RMS. Runs on every inbound frame before turn logic."""

    def __init__(self) -> None:
        self.ns = NoiseSuppressor()
        self.aec = EchoCanceller()
        self.codec = settings.default_codec

    def set_codec(self, offered: list[str]) -> str:
        self.codec = negotiate_codec(offered)
        return self.codec

    def process_frame(self, near_rms: float, far_rms: float = 0.0,
                      speech_threshold: float = 0.02) -> FrameStats:
        cleaned, echo_removed = self.aec.process(near_rms, far_rms)
        suppressed, db = self.ns.process(cleaned)
        return FrameStats(rms=suppressed, is_speech=suppressed >= speech_threshold,
                          suppressed_db=db, echo_removed=echo_removed)
