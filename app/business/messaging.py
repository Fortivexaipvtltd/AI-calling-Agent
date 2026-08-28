from __future__ import annotations

import base64
import urllib.parse
import urllib.request
import uuid

from ..config import settings


class SMSChannel:
    """Outbound SMS. `local` records the send so flows run offline; Twilio SMS
    drops in behind the same `send`."""

    def __init__(self, provider: str | None = None) -> None:
        self.provider = provider or settings.sms_provider
        self.sent: list[dict] = []

    def send(self, to: str, text: str) -> dict:
        if self.provider == "twilio" and settings.twilio_account_sid and settings.sms_from:
            try:
                return self._twilio(to, text)
            except Exception as exc:
                return {"provider": "twilio", "status": "failed", "error": str(exc)}
        msg = {"id": f"sms_{uuid.uuid4().hex[:12]}", "provider": "local",
               "to": to, "text": text, "status": "sent"}
        self.sent.append(msg)
        return msg

    def _twilio(self, to: str, text: str) -> dict:
        sid, tok = settings.twilio_account_sid, settings.twilio_auth_token
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
        body = urllib.parse.urlencode({"To": to, "From": settings.sms_from,
                                       "Body": text}).encode()
        auth = base64.b64encode(f"{sid}:{tok}".encode()).decode()
        req = urllib.request.Request(url, data=body,
                                     headers={"Authorization": f"Basic {auth}"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            import json
            data = json.loads(resp.read().decode())
        return {"provider": "twilio", "id": data.get("sid", ""), "to": to,
                "status": data.get("status", "queued")}


class EmailChannel:
    """Transactional email. `local` records the send; `smtp` sends for real."""

    def __init__(self, provider: str | None = None) -> None:
        self.provider = provider or settings.email_provider
        self.sent: list[dict] = []

    def send(self, to: str, subject: str, body: str) -> dict:
        if self.provider == "smtp" and settings.smtp_host and to:
            try:
                return self._smtp(to, subject, body)
            except Exception as exc:
                return {"provider": "smtp", "status": "failed", "error": str(exc)}
        msg = {"id": f"eml_{uuid.uuid4().hex[:12]}", "provider": "local",
               "to": to, "subject": subject, "body": body, "status": "sent"}
        self.sent.append(msg)
        return msg

    def _smtp(self, to: str, subject: str, body: str) -> dict:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = settings.email_from
        msg["To"] = to
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
            s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.sendmail(settings.email_from, [to], msg.as_string())
        return {"provider": "smtp", "to": to, "subject": subject, "status": "sent"}


sms = SMSChannel()
email = EmailChannel()
