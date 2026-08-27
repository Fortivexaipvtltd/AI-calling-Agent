from __future__ import annotations

import base64
import io
import json


def test_twilio_signature_roundtrip():
    from app.security.webhooks import twilio_signature, verify_twilio
    url = "https://api.example.com/v1/telephony/twilio/status"
    params = {"CallSid": "CA123", "CallStatus": "completed", "From": "+911", "To": "+912"}
    sig = twilio_signature(url, params, auth_token="secrettoken")
    assert verify_twilio(url, params, sig, auth_token="secrettoken")
    assert not verify_twilio(url, params, "wrong", auth_token="secrettoken")
    # tampered params fail
    assert not verify_twilio(url, {**params, "CallStatus": "busy"}, sig, auth_token="secrettoken")


def test_answer_twiml_stream_and_gather():
    from app import config as cfg
    from app.telephony import twilio_voice
    # with a public base url -> Media Stream Connect
    cfg.settings.public_base_url = "https://api.example.com"
    xml = twilio_voice.answer_twiml(opening_line="Hi there", call_id="call_1", stream=True)
    assert "<Stream" in xml and "wss://api.example.com" in xml and "Hi there" in xml
    # without base url -> Gather fallback
    cfg.settings.public_base_url = ""
    xml2 = twilio_voice.answer_twiml(opening_line="Hi again", call_id="call_1", stream=True)
    assert "<Gather" in xml2 and "Hi again" in xml2


def test_twilio_voice_local_fallback_when_unconfigured():
    from app.telephony.twilio_voice import TwilioVoice
    v = TwilioVoice()
    v.sid = ""  # force unconfigured
    res = v.dial("+919999999999", "call_x")
    assert res["provider"] == "local" and res["status"] == "ringing"


def test_twilio_dial_uses_real_api_when_configured(monkeypatch):
    from app.telephony.twilio_voice import TwilioVoice
    v = TwilioVoice()
    v.sid, v.token, v.from_number = "AC_test", "tok", "+911111111111"
    captured = {}

    def fake_urlopen(req, timeout=20):
        captured["url"] = req.full_url
        captured["body"] = req.data.decode()
        return io.BytesIO(json.dumps({"sid": "CA_new", "status": "queued"}).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    res = v.dial("+919999999999", "call_9", amd=True)
    assert res["provider"] == "twilio" and res["provider_call_id"] == "CA_new"
    assert "Calls.json" in captured["url"]
    assert "MachineDetection" in captured["body"]
    assert "To=%2B919999999999" in captured["body"]


def test_deepgram_prerecorded_parses_transcript(monkeypatch):
    from app import config as cfg
    from app.providers.stt import STTProvider
    cfg.settings.stt_api_key = "dg_test"
    payload = {"results": {"channels": [{"alternatives": [
        {"transcript": "i want an ai job", "confidence": 0.98}]}]}}

    def fake_urlopen(req, timeout=20):
        assert req.headers["Authorization"].startswith("Token ")
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    out = STTProvider("deepgram").transcribe(audio=b"\x00\x01", content_type="audio/l16;rate=8000")
    assert out["provider"] == "deepgram" and out["transcript"] == "i want an ai job"
    cfg.settings.stt_api_key = ""


def test_elevenlabs_returns_audio_bytes(monkeypatch):
    from app import config as cfg
    from app.providers.tts import TTSProvider
    cfg.settings.tts_api_key = "el_test"

    def fake_urlopen(req, timeout=20):
        assert req.headers["Xi-api-key"] == "el_test"
        return io.BytesIO(b"ID3fake-mp3-bytes")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    out = TTSProvider("elevenlabs", voice="aarav").synthesize("hello")
    assert out["provider"] == "elevenlabs" and out["audio"].startswith(b"ID3")
    cfg.settings.tts_api_key = ""


def test_media_bridge_transcribes_on_endpoint():
    from app.telephony.media_bridge import MediaBridge

    class FakeSTT:
        def transcribe(self, *, audio=None, content_type=""):
            return {"provider": "fake", "transcript": "hello there"}

    b = MediaBridge(call_id="call_m", stt=FakeSTT())
    b.endpoint_silence_frames = 2
    b.handle_event({"event": "start", "start": {"callSid": "CA"}})
    # a loud PCM16 frame encoded as mu-law -> base64 (speech), then silence
    import audioop
    loud = audioop.lin2ulaw(b"\x40\x30" * 160, 2)  # non-trivial amplitude
    quiet = audioop.lin2ulaw(b"\x00\x00" * 160, 2)
    b.handle_event({"event": "media", "media": {"payload": base64.b64encode(loud).decode()}})
    r1 = b.handle_event({"event": "media", "media": {"payload": base64.b64encode(quiet).decode()}})
    r2 = b.handle_event({"event": "media", "media": {"payload": base64.b64encode(quiet).decode()}})
    result = r1 or r2
    assert result and result["event"] == "transcript" and result["text"] == "hello there"


def test_mulaw_decode_roundtrip():
    import audioop

    from app.telephony.media_bridge import frame_rms, mulaw_to_pcm16
    pcm = b"\x10\x20" * 80
    encoded = audioop.lin2ulaw(pcm, 2)
    decoded = mulaw_to_pcm16(encoded)
    assert len(decoded) == len(pcm)
    assert frame_rms(decoded) > 0


def test_twilio_status_webhook_requires_signature():
    import importlib
    import os
    os.environ["DATABASE_URL"] = "sqlite:////tmp/highh_wh_test.db"
    if os.path.exists("/tmp/highh_wh_test.db"):
        os.remove("/tmp/highh_wh_test.db")
    import app.config as config
    s = config.settings
    s.database_url = os.environ["DATABASE_URL"]
    s.auth_enabled = False
    s.rate_limit_enabled = False
    s.twilio_auth_token = "st"
    s.validate_twilio_signature = True
    s.public_base_url = "https://api.example.com"
    import app.main as main
    importlib.reload(main)
    from fastapi.testclient import TestClient

    from app.security.webhooks import twilio_signature
    with TestClient(main.app) as c:
        params = {"CallSid": "CA1", "CallStatus": "completed"}
        assert c.post("/v1/telephony/twilio/status", data=params).status_code == 403
        sig = twilio_signature("http://testserver/v1/telephony/twilio/status", params,
                               auth_token="st")
        ok = c.post("/v1/telephony/twilio/status", data=params,
                    headers={"X-Twilio-Signature": sig})
        assert ok.status_code == 200 and ok.json()["ok"] is True
    os.environ.pop("DATABASE_URL", None)
