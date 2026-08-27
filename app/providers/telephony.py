from __future__ import annotations

import base64
import json
import urllib.parse
import urllib.request
import uuid

from ..config import settings


class TelephonyProvider:
    """Places the outbound PSTN call. `local` simulates; `twilio` places a
    real call (drop-in). Both return a provider call id."""

    def __init__(self, provider: str | None = None) -> None:
        self.provider = provider or settings.telephony_provider

    def dial(self, to_number: str, answer_url: str = "") -> dict:
        if self.provider == "twilio" and settings.twilio_account_sid:
            try:
                return self._twilio(to_number, answer_url)
            except Exception as exc:
                return {"provider": "twilio", "status": "failed", "error": str(exc)}
        return {"provider": "local", "status": "ringing",
                "provider_call_id": f"sim_{uuid.uuid4().hex[:10]}", "to": to_number}

    def _twilio(self, to_number: str, answer_url: str) -> dict:
        sid, token = settings.twilio_account_sid, settings.twilio_auth_token
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json"
        form = urllib.parse.urlencode({
            "To": to_number, "From": settings.twilio_from_number,
            "Url": answer_url or "http://demo.twilio.com/docs/voice.xml",
        }).encode()
        auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
        req = urllib.request.Request(url, data=form,
                                     headers={"Authorization": f"Basic {auth}"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        return {"provider": "twilio", "status": data.get("status", "queued"),
                "provider_call_id": data.get("sid", ""), "to": to_number}
