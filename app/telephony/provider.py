from __future__ import annotations

from ..config import settings


def active_provider() -> str:
    return (settings.telephony_provider or "local").lower()


def dial(to_number: str, call_ref: str, *, answer_url: str = "") -> dict:
    """Place an outbound call via the configured provider. Returns a normalized
    dict: {provider, status, provider_call_id, to}."""
    prov = active_provider()
    if prov == "exotel":
        from .exotel import voice
        return voice.dial(to_number, call_ref, answer_url=answer_url)
    if prov == "twilio":
        from .twilio_voice import voice
        return voice.dial(to_number, call_ref)
    return {"provider": "local", "status": "queued",
            "provider_call_id": f"local_{call_ref}", "to": to_number}


def hangup(call_sid: str) -> dict:
    prov = active_provider()
    if prov == "exotel":
        from .exotel import voice
        return voice.hangup(call_sid)
    if prov == "twilio":
        from .twilio_voice import voice
        if hasattr(voice, "hangup"):
            return voice.hangup(call_sid)
    return {"ok": True, "provider": "local"}
