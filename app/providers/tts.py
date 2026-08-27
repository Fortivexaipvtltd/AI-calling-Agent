from __future__ import annotations

import json
import urllib.request
from collections.abc import Iterator

from ..config import settings


class TTSProvider:
    """Turns text into speech audio. `local` returns a synthetic marker so the
    system runs offline; `elevenlabs` returns real MP3 bytes (drop-in)."""

    def __init__(self, provider: str | None = None, voice: str = "nova") -> None:
        self.provider = provider or settings.tts_provider
        self.voice = voice

    def synthesize(self, text: str, *, ssml: str = "") -> dict:
        if self.provider == "elevenlabs" and settings.tts_api_key:
            try:
                return self._elevenlabs(text, ssml=ssml)
            except Exception:
                pass
        return {"provider": "local", "voice": self.voice,
                "text": text, "audio_len_ms": max(1, len(text) * 55), "audio": b""}

    def synthesize_stream(self, text: str, *, ssml: str = "") -> Iterator[bytes]:
        """Yield audio as it is produced, for low time-to-first-audio. ElevenLabs
        streams MP3 chunks from its /stream endpoint with latency optimisation;
        the local engine yields synthetic per-clause markers so the pipeline and
        barge-in are exercised offline."""
        if self.provider == "elevenlabs" and settings.tts_api_key:
            try:
                yield from self._elevenlabs_stream(text, ssml=ssml)
                return
            except Exception:
                pass
        for clause in (ssml or text).replace("<break", " <break").split(". "):
            if clause.strip():
                yield f"[audio:{clause.strip()[:24]}]".encode()

    def stream_ulaw(self, text: str, *, ssml: str = "") -> Iterator[bytes]:
        """Yield raw 8 kHz mu-law audio (G.711) — the exact codec Twilio Media
        Streams expects — so TTS output can be sent straight back to the call
        with no resampling. ElevenLabs streams `ulaw_8000` directly; the local
        engine emits proportional mu-law silence so the loop runs offline."""
        if self.provider == "elevenlabs" and settings.tts_api_key:
            try:
                yield from self._elevenlabs_stream(text, ssml=ssml, output_format="ulaw_8000")
                return
            except Exception:
                pass
        # Local: ~55 ms of mu-law per word so frames exist and timing is realistic.
        import audioop
        words = max(1, len((text or "").split()))
        samples = int(8000 * 0.055 * words)      # 8 kHz
        pcm16 = b"\x00\x02" * samples            # very low-amplitude tone (near silence)
        ulaw = audioop.lin2ulaw(pcm16, 2)
        for i in range(0, len(ulaw), 1600):      # ~200 ms blocks
            yield ulaw[i:i + 1600]

    def _payload(self, text: str, ssml: str) -> bytes:
        from ..realtime.voice_profile import profile as vp
        # ElevenLabs accepts SSML when the text contains <speak>…</speak>.
        content = ssml if ssml else text
        return json.dumps({
            "text": content, "model_id": vp.eleven.model_id,
            "voice_settings": {"stability": vp.eleven.stability,
                               "similarity_boost": vp.eleven.similarity_boost,
                               "style": vp.eleven.style,
                               "use_speaker_boost": vp.eleven.use_speaker_boost},
        }).encode()

    def _elevenlabs(self, text: str, ssml: str = "") -> dict:
        voice_id = settings.tts_voice_id or "EXAVITQu4vr4xnSDxMaL"
        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            data=self._payload(text, ssml),
            headers={"content-type": "application/json", "xi-api-key": settings.tts_api_key})
        with urllib.request.urlopen(req, timeout=20) as resp:
            audio = resp.read()
        return {"provider": "elevenlabs", "voice": voice_id, "text": text, "audio": audio}

    def _elevenlabs_stream(self, text: str, ssml: str = "",
                           output_format: str = "") -> Iterator[bytes]:
        from ..realtime.voice_profile import profile as vp
        voice_id = settings.tts_voice_id or "EXAVITQu4vr4xnSDxMaL"
        fmt = output_format or vp.eleven.output_format
        # optimize_streaming_latency trades a little quality for faster first byte.
        url = (f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
               f"?optimize_streaming_latency={vp.eleven.optimize_streaming_latency}"
               f"&output_format={fmt}")
        req = urllib.request.Request(
            url, data=self._payload(text, ssml),
            headers={"content-type": "application/json", "xi-api-key": settings.tts_api_key})
        with urllib.request.urlopen(req, timeout=30) as resp:
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                yield chunk
