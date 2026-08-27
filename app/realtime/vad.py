from __future__ import annotations


class VAD:
    """Voice activity detection. Local stub keyed off audio energy."""

    def __init__(self, threshold: float = 0.02) -> None:
        self.threshold = threshold

    def is_speaking(self, frame_energy: float) -> bool:
        return frame_energy >= self.threshold
