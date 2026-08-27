from __future__ import annotations

import os

from fastapi.testclient import TestClient


def test_call_survives_live_state_loss():
    """Simulate a worker restart / different worker: after clearing the in-memory
    _LIVE map, a turn must rehydrate from the durable snapshot and continue."""
    os.environ["DATABASE_URL"] = "sqlite:////tmp/highh_durability.db"
    os.environ["CALL_WINDOW_START_HOUR"] = "0"
    os.environ["CALL_WINDOW_END_HOUR"] = "24"
    os.environ["AUTH_ENABLED"] = "0"
    os.environ["RATE_LIMIT_ENABLED"] = "0"
    if os.path.exists("/tmp/highh_durability.db"):
        os.remove("/tmp/highh_durability.db")

    import importlib

    import app.config as config
    config.settings.database_url = os.environ["DATABASE_URL"]
    config.settings.call_window_start_hour = 0
    config.settings.call_window_end_hour = 24
    config.settings.auth_enabled = False
    config.settings.rate_limit_enabled = False
    import app.main as main
    importlib.reload(main)

    with TestClient(main.app) as c:
        agent = c.get("/v1/agents").json()["data"][0]["id"]
        lead = c.post("/v1/leads/import",
                      json={"leads": [{"name": "Durable", "phone": "+919000000001"}]}
                      ).json()["data"]["created"][0]
        call = c.post("/v1/calls", json={"lead_id": lead, "agent_id": agent}).json()["data"]
        cid = call["call_id"]
        assert call["state"]

        # First turn through the live map.
        t1 = c.post(f"/v1/calls/{cid}/turn", json={"text": "Yes, good time."}).json()["data"]
        assert t1["state"]

        # Wipe in-memory live state -> forces rehydration from the DB snapshot.
        main._LIVE.clear()

        t2 = c.post(f"/v1/calls/{cid}/turn",
                    json={"text": "I want an AI job in 3 months."}).json()["data"]
        assert t2["state"] and t2["agent"], "rehydrated turn should produce a reply"

        # State should have advanced past the first turn, proving memory carried over.
        assert t2["state"] != "GREETING"

    for k in ("AUTH_ENABLED", "RATE_LIMIT_ENABLED", "CALL_WINDOW_START_HOUR",
              "CALL_WINDOW_END_HOUR", "DATABASE_URL"):
        os.environ.pop(k, None)
