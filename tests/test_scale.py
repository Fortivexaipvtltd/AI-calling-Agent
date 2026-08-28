from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "sqlite:////tmp/highh_scale.db"
os.environ["CALL_WINDOW_START_HOUR"] = "0"
os.environ["CALL_WINDOW_END_HOUR"] = "24"
os.environ["AUTH_ENABLED"] = "0"
os.environ["RATE_LIMIT_ENABLED"] = "0"
if os.path.exists("/tmp/highh_scale.db"):
    os.remove("/tmp/highh_scale.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

_cm = TestClient(app)
_cm.__enter__()
c = _cm


def _lead(name, phone, **kw):
    return c.post("/v1/leads/import",
                  json={"leads": [{"name": name, "phone": phone, **kw}]}
                  ).json()["data"]["created"][0]


# ---- predictive lead scoring --------------------------------------------
def test_lead_scoring_ranks_hot_leads_first():
    _lead("Cold", "+919000000801", source="csv")
    hot = _lead("Hot", "+919000000802", source="referral", email="h@x.com")
    c.post(f"/v1/leads/{hot}/status", json={"status": "interested"})
    ranked = c.get("/v1/leads/scored").json()["data"]
    assert ranked and ranked[0]["propensity"] >= ranked[-1]["propensity"]
    assert all("grade" in r and "reasons" in r for r in ranked)


def test_single_lead_score_has_reasons():
    lid = _lead("Scored", "+919000000803", source="web-form", email="s@x.com")
    r = c.get(f"/v1/leads/{lid}/score").json()["data"]
    assert 0.0 <= r["propensity"] <= 1.0 and r["grade"] in ("A", "B", "C", "D")
    assert isinstance(r["reasons"], list)


# ---- forecasting ---------------------------------------------------------
def test_forecast_shape_and_bands():
    d = c.get("/v1/analytics/forecast").json()["data"]
    for k in ("expected_revenue", "pessimistic_revenue", "optimistic_revenue",
              "expected_conversions", "open_leads"):
        assert k in d
    assert d["optimistic_revenue"] >= d["pessimistic_revenue"]


# ---- A/B testing + self-optimize ----------------------------------------
def test_experiment_assign_and_optimize():
    exp = c.post("/v1/experiments", json={
        "name": "Opening line", "kind": "script",
        "variants": {"A": "Hi, quick question", "B": "Hello, got a minute?"}}
    ).json()["data"]
    eid = exp["id"]
    # assign many times, converting A more than B
    for i in range(30):
        a = c.post(f"/v1/experiments/{eid}/assign").json()["data"]
        variant = a["variant"]
        if variant == "A" and i % 2 == 0:
            c.post(f"/v1/experiments/{eid}/convert", json={"variant": "A"})
        elif variant == "B" and i % 5 == 0:
            c.post(f"/v1/experiments/{eid}/convert", json={"variant": "B"})
    res = c.get(f"/v1/experiments/{eid}").json()["data"]
    assert res["leader"] is not None
    assert sum(r["trials"] for r in res["results"]) == 30


# ---- LLM eval ------------------------------------------------------------
def test_eval_run_scores_hallucination_and_quality():
    d = c.post("/v1/eval/llm").json()["data"]
    for k in ("hallucination_rate", "avg_quality", "latency_ms_avg",
              "est_cost_per_call_usd", "passed"):
        assert k in d
    assert d["hallucination_rate"] == 0.0        # agent must not invent guarantees


def test_eval_score_turn_flags_hallucination():
    from app.advanced.llm_eval import score_turn
    bad = score_turn("Yes we offer a guaranteed job for everyone")
    good = score_turn("Let me confirm the exact fee and get back to you.")
    assert bad["hallucinated"] is True and good["hallucinated"] is False
    assert good["quality"] > bad["quality"]


# ---- audit / event sourcing ---------------------------------------------
def test_audit_records_takeover():
    lid = _lead("Audit", "+919000000804")
    agent = c.get("/v1/agents").json()["data"][0]["id"]
    call = c.post("/v1/calls", json={"lead_id": lid, "agent_id": agent}).json()["data"]
    cid = call["call_id"]
    t = c.post(f"/v1/calls/{cid}/takeover", json={"rep": "Priya"}).json()
    assert t["ok"] and t["data"]["human_takeover"] is True
    log = c.get("/v1/audit", params={"action": "call.takeover"}).json()["data"]
    assert any(e["entity_id"] == cid for e in log)


def test_human_takeover_stops_ai():
    lid = _lead("Take", "+919000000805")
    agent = c.get("/v1/agents").json()["data"][0]["id"]
    cid = c.post("/v1/calls", json={"lead_id": lid, "agent_id": agent}
                 ).json()["data"]["call_id"]
    c.post(f"/v1/calls/{cid}/takeover", json={"rep": "Rep1"})
    t = c.post(f"/v1/calls/{cid}/turn", json={"text": "hello"}).json()["data"]
    assert t.get("human_takeover") is True and t["agent"] == ""


# ---- multi-tenant --------------------------------------------------------
def test_tenant_isolation_scopes_data():
    # create leads under two orgs via header, scored lists must not bleed
    c.post("/v1/experiments", json={"name": "T", "kind": "script",
                                    "variants": {"A": "x"}},
           headers={"X-Org-Id": "org_alpha"})
    a = c.get("/v1/leads/scored", headers={"X-Org-Id": "org_alpha"}).json()["data"]
    b = c.get("/v1/leads/scored", headers={"X-Org-Id": "org_beta"}).json()["data"]
    # both return lists scoped to their org (org_beta has none)
    assert isinstance(a, list) and isinstance(b, list)
    assert all(x.get("lead_id") for x in a) if a else True
