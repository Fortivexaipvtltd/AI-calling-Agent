from __future__ import annotations

import base64
import json
import urllib.parse
import urllib.request
from xml.sax.saxutils import escape

from ..config import settings

# Exotel adapter (India). Two conversation paths:
#   1) Voicebot streaming  — Exotel Voicebot applet opens a WebSocket to us and
#      streams 8k PCM both ways (lowest latency, barge-in). Handled in
#      realtime/exotel_stream.py via the /voicebot WS.
#   2) ExoML passthru      — Exotel hits our /exotel/answer URL, we return XML
#      (<Gather>/<Say>) turn-by-turn. Works on any Exotel account without
#      streaming provisioned. Handled here.
#
# All live execution needs: EXOTEL_SID / EXOTEL_API_KEY / EXOTEL_API_TOKEN /
# EXOTEL_CALLER_ID set, plus a public HTTPS base URL registered in the flow.


def _base() -> str:
    # Exotel REST base uses key:token@subdomain/v1/Accounts/<sid>
    sub = settings.exotel_subdomain or "api.exotel.com"
    return f"https://{sub}/v1/Accounts/{settings.exotel_sid}"


def _auth_header() -> str:
    raw = f"{settings.exotel_api_key}:{settings.exotel_api_token}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def configured() -> bool:
    return bool(settings.exotel_sid and settings.exotel_api_key
                and settings.exotel_api_token and settings.exotel_caller_id)


class ExotelVoice:
    """Outbound calling + ExoML generation for Exotel."""

    def dial(self, to_number: str, call_ref: str, *, answer_url: str = "") -> dict:
        """Place an outbound call. Uses Connect/Call API. When streaming is set up
        the flow (App) drives the bot; otherwise `answer_url` returns ExoML."""
        if not configured():
            # Local fallback so campaign flows run without live telephony.
            return {"provider": "local", "status": "queued",
                    "provider_call_id": f"exo_local_{call_ref}", "to": to_number}
        try:
            url = f"{_base()}/Calls/connect.json"
            data = {
                "From": to_number,
                "CallerId": settings.exotel_caller_id,
                "CallType": "trans",
            }
            # If an App Bazaar flow (voicebot) is configured, connect to it;
            # otherwise point Exotel at our ExoML answer URL.
            if settings.exotel_flow_app_id:
                data["Url"] = (f"http://my.exotel.com/{settings.exotel_sid}/exoml/"
                               f"start_voice/{settings.exotel_flow_app_id}")
            elif answer_url:
                data["Url"] = answer_url
            body = urllib.parse.urlencode(data).encode()
            req = urllib.request.Request(url, data=body,
                                         headers={"Authorization": _auth_header()})
            with urllib.request.urlopen(req, timeout=15) as resp:
                out = json.loads(resp.read().decode())
            call = (out.get("Call") or {})
            return {"provider": "exotel", "status": call.get("Status", "queued"),
                    "provider_call_id": call.get("Sid", ""), "to": to_number}
        except Exception as exc:
            return {"provider": "exotel", "status": "failed", "error": str(exc),
                    "provider_call_id": "", "to": to_number}

    def hangup(self, call_sid: str) -> dict:
        if not configured() or not call_sid:
            return {"ok": True, "provider": "local"}
        try:
            url = f"{_base()}/Calls/{call_sid}.json"
            body = urllib.parse.urlencode({"Status": "completed"}).encode()
            req = urllib.request.Request(url, data=body,
                                         headers={"Authorization": _auth_header()})
            req.get_method = lambda: "POST"
            urllib.request.urlopen(req, timeout=10)
            return {"ok": True, "provider": "exotel"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


voice = ExotelVoice()


# ---- ExoML generation (turn-by-turn passthru) ----------------------------
def answer_exoml(*, opening_line: str, gather_url: str, voice_lang: str = "en-IN") -> str:
    """First response when Exotel connects: greet, then gather the caller's
    speech and post it to our gather_url."""
    say = f"<Say language=\"{voice_lang}\">{escape(opening_line)}</Say>"
    # Exotel supports <Gather> with speech input via the Passthru/Gather applet.
    gather = (f"<Gather action=\"{escape(gather_url)}\" method=\"POST\" "
              f"inputType=\"speech\" timeout=\"5\" language=\"{voice_lang}\">{say}</Gather>")
    return f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response>{gather}</Response>"


def say_and_gather(*, text: str, gather_url: str, voice_lang: str = "en-IN",
                   hangup: bool = False) -> str:
    say = f"<Say language=\"{voice_lang}\">{escape(text)}</Say>"
    if hangup:
        return f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response>{say}<Hangup/></Response>"
    gather = (f"<Gather action=\"{escape(gather_url)}\" method=\"POST\" "
              f"inputType=\"speech\" timeout=\"5\" language=\"{voice_lang}\">{say}</Gather>")
    return f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response>{gather}</Response>"


def parse_status(form: dict) -> dict:
    """Normalize Exotel status-callback params to our internal shape."""
    return {
        "provider_call_id": form.get("CallSid", ""),
        "status": (form.get("Status", "") or "").lower(),
        "from": form.get("From", ""),
        "to": form.get("To", ""),
        "duration_s": int(form.get("DialCallDuration", form.get("Duration", "0")) or 0),
        "recording_url": form.get("RecordingUrl", ""),
    }
