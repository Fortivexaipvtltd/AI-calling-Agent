from __future__ import annotations

import base64
import json
import urllib.request
import uuid

from ..config import settings


class PaymentProvider:
    """Creates payment links (Razorpay) and verifies payment. `local` returns a
    deterministic link + a confirmable payment so the enrolment flow runs offline."""

    def __init__(self, provider: str | None = None) -> None:
        self.provider = provider or settings.payment_provider
        self.links: dict[str, dict] = {}

    def create_link(self, *, amount_inr: int | None = None, name: str = "",
                    phone: str = "", email: str = "", note: str = "") -> dict:
        amount = amount_inr or settings.payment_amount_inr
        if self.provider == "razorpay" and settings.razorpay_key_id:
            try:
                return self._razorpay(amount, name, phone, email, note)
            except Exception as exc:
                return {"provider": "razorpay", "status": "failed", "error": str(exc)}
        pid = f"plink_{uuid.uuid4().hex[:12]}"
        link = {"provider": "local", "payment_id": pid, "amount_inr": amount,
                "status": "created",
                "short_url": f"https://rzp.io/i/{uuid.uuid4().hex[:8]}",
                "upi": f"upi://pay?pa=highh@upi&am={amount}&tn={pid}"}
        self.links[pid] = link
        return link

    def _razorpay(self, amount, name, phone, email, note) -> dict:
        auth = base64.b64encode(
            f"{settings.razorpay_key_id}:{settings.razorpay_key_secret}".encode()).decode()
        body = json.dumps({
            "amount": amount * 100, "currency": "INR", "accept_partial": False,
            "description": note or "Programme enrolment",
            "customer": {"name": name, "contact": phone, "email": email},
            "notify": {"sms": True, "email": bool(email)},
        }).encode()
        req = urllib.request.Request(
            "https://api.razorpay.com/v1/payment_links", data=body,
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        return {"provider": "razorpay", "payment_id": data.get("id", ""),
                "amount_inr": amount, "status": data.get("status", "created"),
                "short_url": data.get("short_url", "")}

    def verify(self, payment_id: str) -> dict:
        """Confirm a payment. Local always confirms (for the demo flow); Razorpay
        would check the payment-link status."""
        if self.provider == "razorpay" and settings.razorpay_key_id:
            try:
                auth = base64.b64encode(
                    f"{settings.razorpay_key_id}:{settings.razorpay_key_secret}".encode()).decode()
                req = urllib.request.Request(
                    f"https://api.razorpay.com/v1/payment_links/{payment_id}",
                    headers={"Authorization": f"Basic {auth}"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode())
                return {"payment_id": payment_id, "status": data.get("status", "created"),
                        "paid": data.get("status") == "paid"}
            except Exception as exc:
                return {"payment_id": payment_id, "status": "error", "paid": False,
                        "error": str(exc)}
        return {"payment_id": payment_id, "status": "paid", "paid": True}


payments = PaymentProvider()


def collect_payment(db, *, lead, amount_inr: int | None = None,
                    channel: str = "whatsapp") -> dict:
    """Create a payment link and send it to the lead."""
    from ..business import outreach
    link = payments.create_link(amount_inr=amount_inr, name=lead.name or "",
                                phone=lead.phone or "", email=lead.email or "")
    url = link.get("short_url", "")
    outreach.send_message(db, lead=lead, channel=channel,
                          text=f"Here's your secure enrolment payment link: {url}",
                          subject="Complete your enrolment", kind="payment_link")
    return link


def confirm_and_convert(db, *, lead, payment_id: str) -> dict:
    """Verify payment; on success mark the lead converted and log it."""
    from ..observability import audit
    result = payments.verify(payment_id)
    if result.get("paid"):
        lead.status = "converted"
        lead.close_probability = 1.0
        db.flush()
        audit.record(db, action="payment.confirmed", entity="lead",
                     entity_id=lead.id, payload={"payment_id": payment_id})
    return {"paid": result.get("paid", False), "lead_status": lead.status,
            "payment_id": payment_id}
