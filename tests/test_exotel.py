from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "sqlite:////tmp/highh_exotel.db"
os.environ["CALL_WINDOW_START_HOUR"] = "0"
os.environ["CALL_WINDOW_END_HOUR"] = "24"
os.environ["AUTH_ENABLED"] = "0"
os.environ["RATE_LIMIT_ENABLED"] = "0"
os.environ["TELEPHONY_PROVIDER"] = "exotel"
if os.path.exists("/tmp/highh_exotel.db"):
    os.remove("/tmp/highh_exotel.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

_cm = TestClient(app)
_cm.__enter__()
c = _cm


# ---- Exotel adapter ------------------------------------------------------
def test_exotel_dial_local_fallback():
    from app.telephony.exotel import voice
    r = voice.dial("+919812345678", "ref1")
    assert r["provider"] in ("local", "exotel") and "provider_call_id" in r


def test_provider_router_selects_exotel():
    import app.config as cf
    cf.settings.telephony_provider = "exotel"
    from app.telephony.provider import active_provider, dial
    assert active_provider() == "exotel"
    r = dial("+919812345678", "ref2")
    assert "provider_call_id" in r


def test_exoml_generation_is_valid_xml():
    from xml.dom.minidom import parseString

    from app.telephony.exotel import answer_exoml, say_and_gather
    x1 = answer_exoml(opening_line="Hi Rahul, is now a good time?",
                      gather_url="https://x/y")
    x2 = say_and_gather(text="Thanks, goodbye.", gather_url="https://x/y", hangup=True)
    parseString(x1)   # raises if malformed
    parseString(x2)
    assert "<Gather" in x1 and "<Hangup" in x2


def test_exotel_status_parsing():
    from app.telephony.exotel import parse_status
    d = parse_status({"CallSid": "abc", "Status": "completed",
                      "DialCallDuration": "42", "From": "+9198", "To": "+9199"})
    assert d["provider_call_id"] == "abc" and d["status"] == "completed"
    assert d["duration_s"] == 42


# ---- Exotel webhooks (turn-by-turn) -------------------------------------
def test_exotel_answer_and_gather_flow():
    r = c.post("/v1/telephony/exotel/answer",
               data={"From": "+919333333333", "CallSid": "CAexo1"})
    assert r.status_code == 200 and "<Gather" in r.text
    # find the created call id from the gather action URL
    import re
    m = re.search(r"call_id=([a-zA-Z0-9_]+)", r.text)
    assert m, "gather url should carry call_id"
    call_id = m.group(1)
    g = c.post(f"/v1/telephony/exotel/gather?call_id={call_id}",
               data={"SpeechResult": "Yes this is a good time"})
    assert g.status_code == 200 and ("<Gather" in g.text or "<Hangup" in g.text)
    leads = c.get("/v1/leads").json()["data"]
    assert any(l["phone"] == "+919333333333" for l in leads)


# ---- Exotel voicebot streaming (text-degrade path) ----------------------
def test_exotel_voicebot_ws_session():
    lid = c.post("/v1/leads/import",
                 json={"leads": [{"name": "Streamer", "phone": "+919444444444"}]}
                 ).json()["data"]["created"][0]
    agent = c.get("/v1/agents").json()["data"][0]["id"]
    call = c.post("/v1/calls", json={"lead_id": lid, "agent_id": agent}).json()["data"]
    cid = call["call_id"]
    with c.websocket_connect(f"/v1/telephony/exotel/voicebot/{cid}") as ws:
        # first frame should be the greeting (agent_text, since no TTS configured)
        first = ws.receive_json()
        assert first["event"] in ("agent_text", "media")
        # send a caller media frame then a stop
        import base64
        silence = base64.b64encode(b"\x00\x00" * 160).decode()
        ws.send_json({"event": "media", "media": {"payload": silence}})
        ws.send_json({"event": "stop"})


# ---- BYO multi-protocol --------------------------------------------------
def test_byo_protocol_detection():
    import app.config as cf
    from app.providers.llm import LLMResponder
    r = LLMResponder(provider="byo")
    cf.settings.byo_protocol = "auto"
    cf.settings.byo_base_url = "https://generativelanguage.googleapis.com/v1beta"
    assert r._detect_protocol() == "gemini"
    cf.settings.byo_base_url = "https://api.openai.com/v1"
    assert r._detect_protocol() == "openai"
    cf.settings.byo_base_url = ""
    cf.settings.byo_api_key = "AIzaSyExample"
    assert r._detect_protocol() == "gemini"
    cf.settings.byo_protocol = "anthropic"
    assert r._detect_protocol() == "anthropic"
    cf.settings.byo_protocol = "auto"
    cf.settings.byo_api_key = ""


def test_byo_falls_back_to_local_without_key():
    import app.config as cf
    from app.providers.llm import LLMResponder
    cf.settings.byo_api_key = ""
    r = LLMResponder(provider="byo")
    line = r.word(intent="greet", lead={"name": "Rahul Sharma"},
                  product={"name": "GenAI Programme", "outcomes": ["AI role"]},
                  memory_facts={}, objection=None, lead_text="", history=[])
    assert isinstance(line, str) and len(line) > 0
