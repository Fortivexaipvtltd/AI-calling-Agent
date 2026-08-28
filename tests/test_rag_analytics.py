from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "sqlite:////tmp/highh_rag.db"
os.environ["CALL_WINDOW_START_HOUR"] = "0"
os.environ["CALL_WINDOW_END_HOUR"] = "24"
os.environ["AUTH_ENABLED"] = "0"
os.environ["RATE_LIMIT_ENABLED"] = "0"
if os.path.exists("/tmp/highh_rag.db"):
    os.remove("/tmp/highh_rag.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

_cm = TestClient(app)
_cm.__enter__()
c = _cm

BROCHURE = ("The Executive GenAI and Agentic AI Programme runs for 24 weeks. "
            "The total fee is 50,000 rupees with EMI options over 6 months. "
            "It includes a 180-Day Better Offer Guarantee: continued support "
            "until a better offer is secured, subject to terms and conditions. "
            "Live classes happen on weekends so working professionals can attend.")


def _ingest():
    return c.post("/v1/knowledge/ingest",
                  json={"title": "Programme Brochure", "text": BROCHURE}).json()


# ---- RAG -----------------------------------------------------------------
def test_ingest_creates_chunks():
    r = _ingest()
    assert r["ok"] and r["data"]["chunks"] >= 2
    docs = c.get("/v1/knowledge").json()["data"]
    assert any(d["title"] == "Programme Brochure" for d in docs)


def test_grounded_answer_uses_document():
    _ingest()
    r = c.post("/v1/knowledge/ask", json={"query": "how long is the programme?"}).json()["data"]
    assert r["grounded"] is True
    assert "24 weeks" in r["answer"] or "weeks" in r["answer"]
    assert r["citations"]


def test_ungrounded_question_does_not_hallucinate():
    _ingest()
    r = c.post("/v1/knowledge/ask",
               json={"query": "what is the capital of Brazil?"}).json()["data"]
    assert r["grounded"] is False
    assert "let me" in r["answer"].lower() or "confirm" in r["answer"].lower()
    assert r["citations"] == []


def test_fee_question_grounded():
    _ingest()
    r = c.post("/v1/knowledge/ask", json={"query": "what are the fees and EMI?"}).json()["data"]
    assert r["grounded"] is True
    assert "50,000" in r["answer"] or "rupees" in r["answer"] or "EMI" in r["answer"]


def test_chunker_splits_on_sentences():
    from app.ai.knowledge import chunk_text
    chunks = chunk_text(BROCHURE, max_chars=120)
    assert len(chunks) >= 2
    assert all(len(x) <= 200 for x in chunks)


# ---- analytics -----------------------------------------------------------
def test_analytics_overview_shape():
    d = c.get("/v1/analytics/overview").json()["data"]
    assert "totals" in d and "by_rep" in d and "by_source" in d
    t = d["totals"]
    for k in ("calls", "connect_rate", "conversion_rate", "talk_minutes",
              "total_cost_usd", "cost_per_call_usd"):
        assert k in t


def test_cost_model_positive():
    from app.business.analytics import call_cost
    assert call_cost(2.0) > call_cost(1.0) > 0


# ---- calendar ------------------------------------------------------------
def test_calendar_availability_and_booking():
    slots = c.post("/v1/calendar/availability", json={}).json()["data"]["slots"]
    assert len(slots) >= 1
    lid = c.post("/v1/leads/import",
                 json={"leads": [{"name": "Book Me", "phone": "+919000000501",
                                  "email": "b@x.com"}]}).json()["data"]["created"][0]
    ev = c.post(f"/v1/leads/{lid}/book",
                json={"title": "Counselling", "when": "tomorrow 5pm",
                      "channel": "whatsapp"}).json()["data"]
    assert ev["status"] == "confirmed" and ev["join_url"]
    acts = c.get(f"/v1/leads/{lid}/activities").json()["data"]
    assert any("booking" in a.get("kind", "") for a in acts)


def test_book_meeting_live_action_creates_event():
    from app.agent_runtime.live_actions import execute
    from app.db import SessionLocal
    from app.models import Lead
    db = SessionLocal()
    try:
        lead = Lead(org_id="org_demo", name="LiveBook", phone="+919000000502",
                    email="lb@x.com", status="new")
        db.add(lead)
        db.flush()
        r = execute(db, lead=lead, action="book_meeting", channel="whatsapp",
                    details={"when": "tomorrow 6pm"})
        assert r["action"] == "book_meeting"
        assert r["event"]["status"] == "confirmed" and r["event"]["join_url"]
    finally:
        db.close()
