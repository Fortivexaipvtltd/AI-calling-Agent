from __future__ import annotations

import json
import urllib.request


class HighhClient:
    """Minimal Python SDK over the REST API. Depends only on the stdlib so it can
    ship as a single file. Mirrors the main resources; extend as endpoints grow.

        client = HighhClient("http://localhost:8000", api_key="...")
        client.import_leads([{"name": "A", "phone": "+91..."}])
        call = client.create_call(lead_id, agent_id)
        client.turn(call["call_id"], "Yes, good time.")
    """

    def __init__(self, base_url: str = "http://localhost:8000", api_key: str = "") -> None:
        self.base = base_url.rstrip("/")
        self.api_key = api_key

    def _req(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())

    # resources ------------------------------------------------------------
    def health(self) -> dict:
        return self._req("GET", "/health")

    def capabilities(self) -> dict:
        return self._req("GET", "/v1/capabilities")

    def import_leads(self, leads: list[dict]) -> dict:
        return self._req("POST", "/v1/leads/import", {"leads": leads})

    def list_leads(self) -> dict:
        return self._req("GET", "/v1/leads")

    def create_agent(self, **kw) -> dict:
        return self._req("POST", "/v1/agents", kw)

    def create_call(self, lead_id: str, agent_id: str) -> dict:
        return self._req("POST", "/v1/calls", {"lead_id": lead_id, "agent_id": agent_id})

    def turn(self, call_id: str, text: str) -> dict:
        return self._req("POST", f"/v1/calls/{call_id}/turn", {"text": text})

    def simulate(self, prospect: str = "interested_price_objection") -> dict:
        return self._req("POST", "/v1/simulate", {"prospect": prospect})

    def send_whatsapp(self, to: str, text: str) -> dict:
        return self._req("POST", "/v1/whatsapp/send", {"to": to, "text": text})
