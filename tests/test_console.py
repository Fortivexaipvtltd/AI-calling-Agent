from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "sqlite:////tmp/highh_console.db"
os.environ["CALL_WINDOW_START_HOUR"] = "0"
os.environ["CALL_WINDOW_END_HOUR"] = "24"
os.environ["AUTH_ENABLED"] = "0"
os.environ["RATE_LIMIT_ENABLED"] = "0"
if os.path.exists("/tmp/highh_console.db"):
    os.remove("/tmp/highh_console.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402  (import after env is set)

_client_cm = TestClient(app)
_client_cm.__enter__()          # fire startup: init_db + seed (2 demo leads)
c = _client_cm


def test_console_html_has_all_sections():
    html = c.get("/").text
    for label in ("Dashboard", "Leads", "AI Calling", "Call History",
                  "Follow-ups", "Agents", "Simulator", "Settings"):
        assert label in html, label


def test_dashboard_metrics():
    base = c.get("/v1/dashboard").json()["data"]["total_leads"]
    c.post("/v1/leads/import", json={"leads": [
        {"name": "A", "phone": "+911"}, {"name": "B", "phone": "+912"}]})
    d = c.get("/v1/dashboard").json()["data"]
    assert d["total_leads"] == base + 2
    assert set(("calls_today", "successful_calls", "followups_due",
                "conversion_rate", "leads_by_status")).issubset(d)


def test_csv_and_web_form_intake():
    base = len(c.get("/v1/leads").json()["data"])
    csv = c.post("/v1/leads/upload-csv", json={
        "csv": "name,phone,email,source\nX,+9111,x@y.com,web\nY,+9122,,ads"}).json()
    assert csv["data"]["created"] == 2
    wf = c.post("/v1/intake/web-form", json={"name": "Z", "phone": "+9133"}).json()
    assert wf["ok"] and wf["data"]["lead_id"]
    assert len(c.get("/v1/leads").json()["data"]) == base + 3


def test_lead_status_transition_and_calls():
    lid = c.post("/v1/leads/import", json={"leads": [{"name": "S", "phone": "+91s"}]}
                 ).json()["data"]["created"][0]
    r = c.post(f"/v1/leads/{lid}/status", json={"status": "qualified"}).json()
    assert r["data"]["status"] == "qualified"
    bad = c.post(f"/v1/leads/{lid}/status", json={"status": "nope"}).json()
    assert bad["ok"] is False
    assert isinstance(c.get(f"/v1/leads/{lid}/calls").json()["data"], list)


def test_followup_complete_and_reschedule():
    lid = c.post("/v1/leads/import", json={"leads": [{"name": "F", "phone": "+91f"}]}
                 ).json()["data"]["created"][0]
    fu = c.post("/v1/followups", json={"lead_id": lid, "reason": "callback",
                                       "channel": "call", "due_in_hours": 1}).json()
    fid = fu["data"]["id"] if fu.get("data") else fu.get("id")
    done = c.post(f"/v1/followups/{fid}/complete").json()
    assert done["data"]["status"] == "completed"
    re = c.post(f"/v1/followups/{fid}/reschedule", json={"in_hours": 48}).json()
    assert re["ok"] and re["data"]["due_at"]


def test_agent_config_get_and_update():
    agent = c.get("/v1/agents").json()["data"][0]["id"]
    cfg = c.get(f"/v1/agents/{agent}/config").json()["data"]
    assert "voices" in cfg and "voice_profiles" in cfg and "business" in cfg
    upd = c.post(f"/v1/agents/{agent}/config",
                 json={"voice": "aarav", "persona": "Warm."}).json()["data"]
    assert upd["voice"] == "aarav" and upd["version"] >= 1


def test_settings_integrations_shape():
    d = c.get("/v1/settings/integrations").json()["data"]
    for k in ("twilio", "deepgram", "elevenlabs", "llm", "whatsapp",
              "database", "auth"):
        assert k in d
    assert "configured" in d["twilio"]


def test_dashboard_reflects_conversion():
    lid = c.post("/v1/leads/import", json={"leads": [{"name": "C", "phone": "+91c"}]}
                 ).json()["data"]["created"][0]
    c.post(f"/v1/leads/{lid}/status", json={"status": "converted"})
    d = c.get("/v1/dashboard").json()["data"]
    assert d["conversion_rate"] > 0
    assert d["leads_by_status"].get("converted") >= 1
