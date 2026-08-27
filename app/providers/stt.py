from __future__ import annotations

import json
import urllib.request

from ..config import settings


class STTProvider:
    """Speech-to-text (listening). `local` transcribes from supplied words so the
    system runs offline; `deepgram` sends audio bytes to Deepgram's streaming/
    prerecorded API for real recognition (drop-in). Falls back on any error."""

    def __init__(self, provider: str | None = None) -> None:
        self.provider = provider or settings.stt_provider

    def transcribe(self, *, words: list[str] | None = None,
                   audio: bytes | None = None, content_type: str = "audio/wav") -> dict:
        if self.provider == "deepgram" and settings.stt_api_key and audio:
            try:
                return self._deepgram(audio, content_type)
            except Exception:
                pass
        text = " ".join(words or []).strip()
        return {"provider": "local", "transcript": text, "confidence": 1.0, "is_final": True}

    def _deepgram(self, audio: bytes, content_type: str) -> dict:
        params = "model=nova-2&smart_format=true&punctuate=true&language=en"
        # Raw linear PCM (from the Twilio media bridge) needs explicit encoding.
        if "l16" in content_type or "linear16" in content_type:
            rate = "8000"
            if "rate=" in content_type:
                rate = content_type.split("rate=")[-1].split(";")[0].strip() or "8000"
            params += f"&encoding=linear16&sample_rate={rate}"
            header_ct = "audio/l16"
        else:
            header_ct = content_type
        url = f"https://api.deepgram.com/v1/listen?{params}"
        req = urllib.request.Request(
            url, data=audio,
            headers={"Authorization": f"Token {settings.stt_api_key}",
                     "Content-Type": header_ct})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        alt = data["results"]["channels"][0]["alternatives"][0]
        return {"provider": "deepgram", "transcript": alt.get("transcript", ""),
                "confidence": alt.get("confidence", 0.0), "is_final": True}
