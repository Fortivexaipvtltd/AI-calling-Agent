from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "sqlite:////tmp/highh_ops.db"
os.environ["CALL_WINDOW_START_HOUR"] = "0"
os.environ["CALL_WINDOW_END_HOUR"] = "24"
os.environ["AUTH_ENABLED"] = "0"
os.environ["RATE_LIMIT_ENABLED"] = "0"
if os.path.exists("/tmp/highh_ops.db"):
    os.remove("/tmp/highh_ops.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

_cm = TestClient(app)
_cm.__enter__()
c = _cm


def _lead(name, phone, **kw):
    return c.post("/v1/leads/import",
                  json={"leads": [{"name": name, "phone": phone, **kw}]}
                  ).json()["data"]["created"][0]


# ---- payments ------------------------------------------------------------
def test_payment_link_and_confirm_converts():
    lid = _lead("Payer", "+919000000901", email="p@x.com")
    link = c.post(f"/v1/leads/{lid}/payment-link", json={"channel": "whatsapp"}).json()
    assert link["ok"] and link["data"]["short_url"]
    pid = link["data"]["payment_id"]
    conf = c.post(f"/v1/leads/{lid}/confirm-payment", json={"payment_id": pid}).json()
    assert conf["data"]["paid"] is True
    lead = c.get(f"/v1/leads/{lid}").json()["data"]
    assert lead["status"] == "converted"


# ---- embeddings RAG ------------------------------------------------------
def test_embeddings_improve_retrieval():
    from app.ai.embeddings import cosine, embed
    v = embed(["programme fee is 50000 rupees with EMI",
               "the weather is sunny today"])
    q = embed(["what are the fees and EMI?"])[0]
    # the fee sentence should be closer than the weather sentence
    assert cosine(q, v[0]) > cosine(q, v[1])


def test_grounded_answer_via_embeddings():
    c.post("/v1/knowledge/ingest", json={
        "title": "Fees", "text": "The total programme fee is 50,000 rupees with "
        "EMI options over six months. Placement support is included."})
    r = c.post("/v1/knowledge/ask", json={"query": "how much are the fees?"}).json()["data"]
    assert r["grounded"] is True


# ---- monitoring ----------------------------------------------------------
def test_monitoring_snapshot_and_alert():
    from app.observability.monitoring import Monitor
    m = Monitor()
    for _ in range(12):
        m.record_call(ok=False, latency_ms=2000, cost_usd=1.0)
    snap = m.snapshot()
    assert snap["calls"] == 12 and snap["failure_rate"] > 0.3
    assert any(a["kind"] in ("high_latency", "high_cost", "high_failure_rate")
               for a in snap["recent_alerts"])
    assert c.get("/v1/monitoring").json()["data"] is not None


# ---- cost dashboard / reps / export -------------------------------------
def test_cost_breakdown_shape():
    d = c.get("/v1/analytics/cost").json()["data"]
    for k in ("twilio_usd", "deepgram_usd", "elevenlabs_usd", "llm_usd", "total_usd"):
        assert k in d


def test_rep_performance_and_export():
    reps = c.get("/v1/analytics/reps").json()["data"]
    assert isinstance(reps, list)
    csv = c.get("/v1/analytics/export.csv")
    assert csv.status_code == 200 and "call_id" in csv.text


# ---- inbound call + whatsapp bot ----------------------------------------
def test_inbound_call_creates_lead_and_twiml():
    r = c.post("/v1/telephony/twilio/inbound",
               data={"From": "+919111111111", "CallSid": "CAinbound1"})
    assert r.status_code == 200 and ("Say" in r.text or "Stream" in r.text or "Gather" in r.text)
    leads = c.get("/v1/leads").json()["data"]
    assert any(l["phone"] == "+919111111111" for l in leads)


def test_whatsapp_inbound_bot_replies():
    c.post("/v1/knowledge/ingest", json={
        "title": "Duration", "text": "The programme runs for 24 weeks on weekends."})
    r = c.post("/v1/telephony/twilio/whatsapp/inbound",
               data={"From": "whatsapp:+919222222222", "Body": "how long is the programme?"}
               ).json()
    assert r["ok"] and r["data"]["reply"]


# ---- recording + consent -------------------------------------------------
def test_recording_endpoint():
    r = c.get("/v1/calls/CA123/recording").json()
    assert r["ok"] and "recording_url" in r["data"]


def test_consent_logged_to_audit():
    lid = _lead("Consent", "+919000000902")
    c.post("/v1/compliance/consent", json={"lead_id": lid, "consent": True})
    log = c.get("/v1/audit", params={"action": "consent.captured"}).json()["data"]
    assert any(e["entity_id"] == lid for e in log)


# ---- live sentiment + next-best-action ----------------------------------
def test_call_turn_returns_sentiment_and_nba():
    lid = _lead("Senti", "+919000000903")
    agent = c.get("/v1/agents").json()["data"][0]["id"]
    cid = c.post("/v1/calls", json={"lead_id": lid, "agent_id": agent}
                 ).json()["data"]["call_id"]
    t = c.post(f"/v1/calls/{cid}/turn",
               json={"text": "Yes I love this, I want to enroll and pay now!"}
               ).json()["data"]
    assert "signals" in t and t["signals"] is not None
    assert t["signals"]["sentiment"] in ("positive", "neutral", "negative")
    assert "next_best_action" in t["signals"]
