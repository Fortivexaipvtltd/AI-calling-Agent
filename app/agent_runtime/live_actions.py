from __future__ import annotations

import re

# Detects when the agent (or lead) has triggered a real-world action during a
# call, and executes it: send brochure, send a quote, book a meeting + share the
# link, or send a payment link. Each returns a compact record for the transcript.

_BROCHURE = re.compile(r"\b(brochure|prospectus|details|curriculum|syllabus)\b", re.I)
_QUOTE = re.compile(r"\b(quote|price|pricing|fees?|cost|emi)\b", re.I)
_BOOK = re.compile(r"\b(book|schedule|slot|appointment|meeting|demo|counsell?or call)\b", re.I)
_PAYLINK = re.compile(r"\b(pay|payment|enroll|enrol|register|link to pay)\b", re.I)
_SEND_INTENT = re.compile(r"\b(send|share|whatsapp|email|text|sms)\b", re.I)


def detect_actions(agent_text: str, lead_text: str = "") -> list[str]:
    """Return the action names implied by this turn. The agent offering to send
    something ('can I send you the brochure?') or the lead asking counts."""
    joined = f"{agent_text} {lead_text}"
    actions = []
    if _BROCHURE.search(joined) and (_SEND_INTENT.search(joined) or "?" in agent_text):
        actions.append("send_brochure")
    if _QUOTE.search(joined) and _SEND_INTENT.search(joined):
        actions.append("send_quote")
    if _BOOK.search(joined):
        actions.append("book_meeting")
    if _PAYLINK.search(joined) and _SEND_INTENT.search(joined):
        actions.append("send_payment_link")
    return actions


def channel_from_text(text: str, default: str = "whatsapp") -> str:
    t = text.lower()
    if "email" in t:
        return "email"
    if "sms" in t or "text" in t:
        return "sms"
    if "whatsapp" in t:
        return "whatsapp"
    return default


def execute(db, *, lead, action: str, channel: str = "whatsapp",
            details: dict | None = None) -> dict:
    """Execute a detected action for real (records to the CRM timeline)."""
    from ..business import outreach
    details = details or {}
    if action == "send_brochure":
        r = outreach.send_brochure(db, lead=lead, channel=channel)
        return {"action": action, **r}
    if action == "send_quote":
        r = outreach.send_quote(db, lead=lead, plan=details.get("plan", "Full programme"),
                                amount=details.get("amount", "₹50,000"), channel=channel)
        return {"action": action, **r}
    if action == "book_meeting":
        from ..business.calendar import calendar
        when = details.get("when", "tomorrow 5pm")
        ev = calendar.book(title="Admissions counselling call",
                           when_iso=details.get("when_iso", ""),
                           attendee_email=getattr(lead, "email", "") or "",
                           attendee_name=getattr(lead, "name", "") or "")
        r = outreach.send_booking_link(db, lead=lead, when=when,
                                       link=ev.get("join_url", ""), channel=channel)
        return {"action": action, "when": when, "event": ev, **r}
    if action == "send_payment_link":
        link = details.get("link", "")
        from ..config import settings
        link = link or f"{settings.public_base_url or settings.brochure_url}/pay"
        r = outreach.send_message(db, lead=lead, channel=channel,
                                  text=f"Here's your secure enrolment link: {link}",
                                  subject="Complete your enrolment", kind="payment_link")
        return {"action": action, **r}
    return {"action": action, "ok": False, "error": "unknown_action"}


def run_detected(db, *, lead, agent_text: str, lead_text: str = "") -> list[dict]:
    """Detect actions in a turn and execute them, choosing the channel the lead
    referenced (falls back to WhatsApp). Returns records for the transcript."""
    done = []
    channel = channel_from_text(f"{agent_text} {lead_text}")
    for action in detect_actions(agent_text, lead_text):
        done.append(execute(db, lead=lead, action=action, channel=channel))
    return done
