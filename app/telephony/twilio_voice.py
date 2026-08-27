from __future__ import annotations

import base64
import json
import urllib.parse
import urllib.request
from xml.sax.saxutils import escape

from ..config import settings


def _base_url() -> str:
    return settings.public_base_url.rstrip("/") if getattr(settings, "public_base_url", "") else ""


def answer_twiml(*, opening_line: str, call_id: str, stream: bool = True) -> str:
    """TwiML returned to Twilio when the callee answers.

    If `stream` and a public base URL is configured, we open a Media Stream to
    our WebSocket bridge for real-time STT. Otherwise we fall back to a
    <Gather input="speech"> loop that posts recognised speech back to us — both
    are valid production flows; the stream path is lower latency.
    """
    say = f"<Say voice=\"Polly.Aditi\">{escape(opening_line)}</Say>"
    base = _base_url()
    if stream and base:
        ws = base.replace("https://", "wss://").replace("http://", "ws://")
        return (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<Response>"
            f"{say}"
            "<Connect>"
            f"<Stream url=\"{ws}/v1/telephony/twilio/media/{call_id}\"/>"
            "</Connect>"
            "</Response>"
        )
    action = f"{base}/v1/telephony/twilio/gather/{call_id}" if base else ""
    gather = (f"<Gather input=\"speech\" speechTimeout=\"auto\" method=\"POST\""
              f"{f' action=\"{action}\"' if action else ''}>{say}</Gather>")
    return f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response>{gather}</Response>"


def say_twiml(text: str, *, hangup: bool = False) -> str:
    body = f"<Say voice=\"Polly.Aditi\">{escape(text)}</Say>"
    if hangup:
        body += "<Hangup/>"
    return f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response>{body}</Response>"


class TwilioVoice:
    """Real outbound dialing that points Twilio at our own answer TwiML, with
    answering-machine detection and recording enabled. Local fallback keeps the
    stack runnable without credentials."""

    def __init__(self) -> None:
        self.sid = settings.twilio_account_sid
        self.token = settings.twilio_auth_token
        self.from_number = settings.twilio_from_number

    def configured(self) -> bool:
        return bool(self.sid and self.token and self.from_number)

    def dial(self, to_number: str, call_id: str, *, amd: bool = True,
             record: bool | None = None) -> dict:
        if not self.configured():
            return {"provider": "local", "status": "ringing",
                    "provider_call_id": f"sim_{call_id}", "to": to_number}
        base = _base_url()
        answer_url = f"{base}/v1/telephony/twilio/answer/{call_id}" if base else \
            "http://demo.twilio.com/docs/voice.xml"
        params = {
            "To": to_number, "From": self.from_number, "Url": answer_url,
            "StatusCallback": f"{base}/v1/telephony/twilio/status" if base else "",
            "StatusCallbackEvent": "initiated ringing answered completed",
        }
        if amd:
            params["MachineDetection"] = "DetectMessageEnd"
        if record if record is not None else settings.recording_enabled:
            params["Record"] = "true"
            if base:
                params["RecordingStatusCallback"] = f"{base}/v1/telephony/twilio/recording"
        params = {k: v for k, v in params.items() if v != ""}
        try:
            data = self._post_call(params)
            return {"provider": "twilio", "status": data.get("status", "queued"),
                    "provider_call_id": data.get("sid", ""), "to": to_number}
        except Exception as exc:
            return {"provider": "twilio", "status": "failed", "error": str(exc)}

    def _post_call(self, params: dict) -> dict:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Calls.json"
        body = urllib.parse.urlencode(params).encode()
        auth = base64.b64encode(f"{self.sid}:{self.token}".encode()).decode()
        req = urllib.request.Request(url, data=body,
                                     headers={"Authorization": f"Basic {auth}"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())


def parse_status(form: dict) -> dict:
    """Normalise a Twilio status callback into our internal shape."""
    return {
        "provider_call_id": form.get("CallSid", ""),
        "status": form.get("CallStatus", ""),
        "answered_by": form.get("AnsweredBy", ""),   # human | machine_* when AMD on
        "duration_s": int(form.get("CallDuration", "0") or 0),
        "from": form.get("From", ""),
        "to": form.get("To", ""),
    }


voice = TwilioVoice()
