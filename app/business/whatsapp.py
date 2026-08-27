from __future__ import annotations

import json
import urllib.request
import uuid

from ..config import settings


class WhatsAppProvider:
    """WhatsApp Business messaging. `local` records the send so flows run offline;
    Meta Cloud API / Twilio WhatsApp drop in behind the same `send`. Supports
    free-form text and approved template messages."""

    def __init__(self, provider: str | None = None) -> None:
        self.provider = provider or settings.whatsapp_provider
        self.sent: list[dict] = []

    def send(self, to: str, *, text: str = "", template: str = "",
             variables: dict | None = None) -> dict:
        if self.provider == "meta" and settings.whatsapp_token:
            try:
                return self._meta(to, text, template, variables or {})
            except Exception as exc:
                return {"provider": "meta", "status": "failed", "error": str(exc)}
        msg = {"id": f"wamid_{uuid.uuid4().hex[:12]}", "provider": "local", "to": to,
               "text": text, "template": template, "variables": variables or {},
               "status": "sent"}
        self.sent.append(msg)
        return msg

    def _meta(self, to: str, text: str, template: str, variables: dict) -> dict:
        url = f"https://graph.facebook.com/v20.0/{settings.whatsapp_phone_id}/messages"
        if template:
            payload = {"messaging_product": "whatsapp", "to": to, "type": "template",
                       "template": {"name": template, "language": {"code": "en"}}}
        else:
            payload = {"messaging_product": "whatsapp", "to": to, "type": "text",
                       "text": {"body": text}}
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"content-type": "application/json",
                     "authorization": f"Bearer {settings.whatsapp_token}"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        return {"provider": "meta", "status": "sent",
                "id": data.get("messages", [{}])[0].get("id", "")}


whatsapp = WhatsAppProvider()
