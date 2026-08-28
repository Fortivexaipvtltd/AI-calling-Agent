from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ..config import settings
from .messaging import email as email_ch
from .messaging import sms as sms_ch
from .whatsapp import WhatsAppProvider

_wa = WhatsAppProvider()

CHANNELS = ("whatsapp", "sms", "email")


def _record(db, lead_id: str, channel: str, kind: str, detail: dict) -> None:
    """Log every send to the activity timeline so the CRM shows what went out."""
    try:
        import json

        from ..models import Activity
        db.add(Activity(lead_id=lead_id, org_id=settings.default_org_id,
                        kind=f"message.{kind}",
                        body=json.dumps({"channel": channel, **detail})))
        db.flush()
    except Exception:
        pass


def send_message(db, *, lead, channel: str, text: str = "", subject: str = "",
                 template: str = "", kind: str = "message") -> dict:
    """Send one message on a channel, recording it. Falls back to a channel the
    lead can receive on if the requested one has no address."""
    channel = channel if channel in CHANNELS else "whatsapp"
    to_phone = getattr(lead, "phone", "") or ""
    to_email = getattr(lead, "email", "") or ""
    if channel == "email" and not to_email:
        channel = "whatsapp" if to_phone else "sms"
    if channel in ("whatsapp", "sms") and not to_phone and to_email:
        channel = "email"

    if channel == "whatsapp":
        res = _wa.send(to_phone, text=text, template=template)
    elif channel == "sms":
        res = sms_ch.send(to_phone, text)
    else:
        res = email_ch.send(to_email, subject or "From the admissions desk", text)
    _record(db, lead.id, channel, kind, {"status": res.get("status"),
                                         "id": res.get("id", "")})
    return {"channel": channel, "result": res}


def send_brochure(db, *, lead, channel: str = "whatsapp") -> dict:
    text = (f"Hi {lead.name.split()[0] if lead.name else 'there'}, here's the "
            f"programme brochure as promised: {settings.brochure_url}")
    return send_message(db, lead=lead, channel=channel, text=text,
                        subject="Your programme brochure", kind="brochure")


def send_quote(db, *, lead, plan: str, amount: str, channel: str = "whatsapp") -> dict:
    text = (f"Here's the quote you asked for — {plan}: {amount}. "
            f"Reply here if you'd like the EMI breakdown.")
    return send_message(db, lead=lead, channel=channel, text=text,
                        subject="Your quote", kind="quote")


def send_booking_link(db, *, lead, when: str = "", link: str = "",
                      channel: str = "whatsapp") -> dict:
    link = link or f"{settings.public_base_url or settings.brochure_url}"
    text = (f"You're booked{f' for {when}' if when else ''}. "
            f"Here's your meeting link: {link}. See you then!")
    return send_message(db, lead=lead, channel=channel, text=text,
                        subject="Your booking is confirmed", kind="booking")


# ---- omnichannel follow-up sequences -------------------------------------
# A sequence is an ordered list of steps; each becomes a Followup row so the
# scheduler fires it at the right time on the right channel.
SEQUENCES = {
    "post_call_nurture": [
        {"in_hours": 0, "channel": "whatsapp", "kind": "brochure"},
        {"in_hours": 24, "channel": "whatsapp", "reason": "check if reviewed",
         "kind": "nudge"},
        {"in_hours": 72, "channel": "email", "reason": "share success stories",
         "kind": "nudge"},
        {"in_hours": 120, "channel": "sms", "reason": "final reminder",
         "kind": "nudge"},
    ],
    "no_answer_retry": [
        {"in_hours": 2, "channel": "whatsapp", "reason": "missed you", "kind": "nudge"},
        {"in_hours": 24, "channel": "sms", "reason": "best time to talk?",
         "kind": "nudge"},
    ],
}


def enroll_sequence(db, *, lead, sequence: str, immediate_send=None) -> dict:
    """Schedule a follow-up sequence for a lead. Step 0 with in_hours==0 is sent
    immediately; the rest are scheduled as Followup rows."""
    from ..models import Followup
    steps = SEQUENCES.get(sequence)
    if not steps:
        return {"ok": False, "error": "unknown_sequence"}
    now = datetime.now(UTC)
    scheduled, sent = 0, 0
    for step in steps:
        if step["in_hours"] == 0 and step.get("kind") == "brochure":
            send_brochure(db, lead=lead, channel=step["channel"])
            sent += 1
            continue
        fu = Followup(org_id=getattr(lead, "org_id", ""), lead_id=lead.id,
                      due_at=now + timedelta(hours=step["in_hours"]),
                      reason=step.get("reason", step.get("kind", "follow up")),
                      channel=step["channel"], status="scheduled")
        db.add(fu)
        scheduled += 1
    db.flush()
    return {"ok": True, "sequence": sequence, "scheduled": scheduled, "sent": sent}
