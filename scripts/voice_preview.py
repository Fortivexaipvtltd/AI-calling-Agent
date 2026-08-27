from __future__ import annotations

"""Ear-tuning helper. With an ElevenLabs key set (TTS_PROVIDER=elevenlabs,
TTS_API_KEY=..., optionally TTS_VOICE_ID=...), this writes one MP3 per sample
line per intent so you can LISTEN and adjust app/realtime/voice_profile.py.

    TTS_PROVIDER=elevenlabs TTS_API_KEY=sk_... python -m scripts.voice_preview
    # -> voice_samples/<preset>/<intent>.mp3  + a report of time-to-first-audio

Without a key it still runs and prints the SSML + timing using the local engine,
so you can sanity-check pacing offline.
"""

import os
import time

from app.config import settings
from app.providers.tts import TTSProvider
from app.realtime import voice_profile
from app.realtime.prosody import ProsodyEngine

SAMPLES = {
    "discover": "Hi Rahul, thanks for taking my call. What's prompting you to look at this now?",
    "empathy": "I completely understand — fees are a real consideration, and I don't want to rush you.",
    "objection": "That's a fair concern about the price. Here's how the guarantee protects you.",
    "confirm": "Perfect. Your seat is booked and I've texted the ₹50,000 EMI link to you now.",
}


def _synth_to_file(tts: TTSProvider, ssml: str, text: str, path: str) -> tuple[int, float]:
    start = time.perf_counter()
    first = None
    total = bytearray()
    for chunk in tts.synthesize_stream(text, ssml=ssml):
        if first is None:
            first = time.perf_counter()
        total += chunk if isinstance(chunk, (bytes, bytearray)) else str(chunk).encode()
    ttfa = ((first - start) * 1000) if first else 0.0
    if tts.provider == "elevenlabs" and total[:2] in (b"ID", b"\xff\xfb", b"\xff\xf3"):
        with open(path, "wb") as f:
            f.write(total)
    return len(total), ttfa


def main() -> None:
    presets = list(voice_profile.PRESETS)
    live = settings.tts_provider == "elevenlabs" and bool(settings.tts_api_key)
    print(f"provider={'elevenlabs' if live else 'local(no key)'}  presets={presets}\n")
    prosody = ProsodyEngine()
    for preset in presets:
        os.environ["VOICE_PROFILE"] = preset
        voice_profile.profile = voice_profile.load_profile()
        outdir = os.path.join("voice_samples", preset)
        os.makedirs(outdir, exist_ok=True)
        print(f"[{preset}]")
        tts = TTSProvider("elevenlabs" if live else "local")
        for intent, line in SAMPLES.items():
            ssml = prosody.to_ssml(line, intent=intent)
            path = os.path.join(outdir, f"{intent}.mp3")
            size, ttfa = _synth_to_file(tts, ssml, line, path)
            where = path if (live and size) else "(ssml only)"
            print(f"  {intent:9s} ttfa={ttfa:6.1f}ms  {where}")
            if not live:
                print(f"            {ssml}")
        print()
    if live:
        print("Listen to voice_samples/<preset>/*.mp3, then edit "
              "app/realtime/voice_profile.py (pauses, rate, pitch, eleven.style).")
    else:
        print("Set TTS_PROVIDER=elevenlabs and TTS_API_KEY to render real MP3s.")


if __name__ == "__main__":
    main()
