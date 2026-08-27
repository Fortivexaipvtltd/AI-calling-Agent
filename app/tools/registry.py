from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta

from ..events import bus


def _id(p: str) -> str:
    return f"{p}_{uuid.uuid4().hex[:10]}"


class ToolRegistry:
    """All agent tools from the blueprint. Backed by a pluggable store so it
    runs standalone (in-memory) or against the DB service layer."""

    def __init__(self, store: dict | None = None) -> None:
        self.store = store if store is not None else {
            "leads": {}, "facts": {}, "products": {}, "followups": {},
            "appointments": {}, "deals": {}, "activities": {}, "payments": {},
            "messages": {}, "suppressions": {}, "handoffs": {},
        }
        self._tools: dict[str, Callable] = {}
        self._register_all()

    # ---- dispatch ---------------------------------------------------------
    def call(self, name: str, args: dict | None = None) -> dict:
        args = args or {}
        fn = self._tools.get(name)
        if not fn:
            return {"ok": False, "error": f"unknown_tool:{name}"}
        try:
            return {"ok": True, "result": fn(args)}
        except Exception as exc:  # tools never crash the runtime
            return {"ok": False, "error": str(exc)}

    def register(self, name: str, fn: Callable) -> None:
        self._tools[name] = fn

    def names(self) -> list[str]:
        return sorted(self._tools)

    # ---- registrations ----------------------------------------------------
    def _register_all(self) -> None:
        s = self.store
        r = self.register

        # lead.*
        r("lead.get", lambda a: s["leads"].get(a["lead_id"], {"id": a.get("lead_id")}))
        r("lead.update", lambda a: s["leads"].setdefault(a["lead_id"], {"id": a["lead_id"]}).update(
            {k: v for k, v in a.items() if k != "lead_id"}) or s["leads"][a["lead_id"]])
        r("lead.add_fact", lambda a: self._add_fact(a))
        r("lead.get_memory", lambda a: s["facts"].get(a["lead_id"], {}))

        # product.*
        r("product.get", lambda a: s["products"].get(a.get("product_id"), {}))
        r("product.search_faq", lambda a: self._search_faq(a))
        r("product.get_pricing", lambda a: s["products"].get(a.get("product_id"), {}).get("pricing_plans", []))
        r("product.check_eligibility", lambda a: {"eligible": True, "reasons": []})

        # calendar.*
        r("calendar.check", lambda a: {"slots": ["tomorrow 5pm", "tomorrow 6pm", "sat 11am"]})
        r("calendar.book", lambda a: self._book(a))
        r("calendar.cancel", lambda a: self._cancel_appt(a))

        # followup.*
        r("followup.create", lambda a: self._followup(a))
        r("followup.reschedule", lambda a: self._reschedule(a))
        r("followup.cancel", lambda a: self._cancel_followup(a))

        # message.*
        r("message.send_sms", lambda a: self._message("sms", a))
        r("message.send_email", lambda a: self._message("email", a))

        # deal.* / payment.*
        r("deal.create", lambda a: self._deal(a))
        r("deal.update", lambda a: self._deal_update(a))
        r("payment.create_link", lambda a: self._payment(a))
        r("payment.get_status", lambda a: s["payments"].get(a.get("payment_id"), {"status": "pending"}))

        # crm.*
        r("crm.add_activity", lambda a: self._activity(a["lead_id"], a.get("kind", "note"), a.get("body", "")))
        r("crm.add_note", lambda a: self._activity(a["lead_id"], "note", a.get("body", "")))

        # human.*
        r("human.transfer", lambda a: self._transfer(a))
        r("human.create_callback", lambda a: self._followup({**a, "reason": "callback", "channel": "call"}))

        # call.*
        r("call.end", lambda a: {"call_id": a.get("call_id"), "ended": True})
        r("call.record_outcome", lambda a: {"call_id": a.get("call_id"), "outcome": a.get("outcome", "")})

        # compliance.*
        r("compliance.check_call_permission", lambda a: {"allowed": a["lead_id"] not in s["suppressions"]})
        r("compliance.suppress_lead", lambda a: self._suppress(a))

        # message.* (extended channel) + telephony control + ai retrieval
        r("message.send_whatsapp", lambda a: self._whatsapp(a))
        r("telephony.start_recording", lambda a: self._recording_start(a))
        r("telephony.stop_recording", lambda a: self._recording_stop(a))
        r("telephony.warm_transfer", lambda a: self._warm_transfer(a))
        r("telephony.cold_transfer", lambda a: self._cold_transfer(a))
        r("telephony.conference", lambda a: self._conference(a))
        r("telephony.drop_voicemail", lambda a: self._voicemail(a))
        r("telephony.detect_machine", lambda a: self._amd(a))
        r("rag.search", lambda a: {"hits": self._rag_search(a)})
        r("mcp.call", lambda a: self._mcp_call(a))

    # ---- implementations --------------------------------------------------
    def _add_fact(self, a: dict) -> dict:
        lead_facts = self.store["facts"].setdefault(a["lead_id"], {})
        lead_facts[a["key"]] = a["value"]
        bus.emit("conversation.fact_extracted", {"lead_id": a["lead_id"], "key": a["key"]})
        return {"lead_id": a["lead_id"], "key": a["key"], "value": a["value"]}

    def _search_faq(self, a: dict) -> dict:
        product = self.store["products"].get(a.get("product_id"), {})
        q = a.get("query", "").lower()
        for faq in product.get("faqs", []):
            if q and q in faq.get("q", "").lower():
                return faq
        return {"q": q, "a": "Let me get you the exact approved detail on that."}

    def _book(self, a: dict) -> dict:
        appt = {"id": _id("appt"), "lead_id": a["lead_id"], "slot": a.get("slot", "tomorrow 5pm"),
                "status": "booked", "at": datetime.utcnow().isoformat()}
        self.store["appointments"][appt["id"]] = appt
        bus.emit("appointment.booked", appt)
        return appt

    def _cancel_appt(self, a: dict) -> dict:
        appt = self.store["appointments"].get(a.get("appointment_id"))
        if appt:
            appt["status"] = "cancelled"
        return appt or {"cancelled": False}

    def _followup(self, a: dict) -> dict:
        fu = {"id": _id("fu"), "lead_id": a["lead_id"], "reason": a.get("reason", ""),
              "channel": a.get("channel", "call"), "status": "scheduled",
              "due_at": (datetime.utcnow() + timedelta(hours=a.get("due_in_hours", 24))).isoformat()}
        self.store["followups"][fu["id"]] = fu
        bus.emit("followup.created", fu)
        return fu

    def _reschedule(self, a: dict) -> dict:
        fu = self.store["followups"].get(a.get("followup_id"))
        if fu:
            fu["due_at"] = (datetime.utcnow() + timedelta(hours=a.get("due_in_hours", 24))).isoformat()
        return fu or {"rescheduled": False}

    def _cancel_followup(self, a: dict) -> dict:
        fu = self.store["followups"].get(a.get("followup_id"))
        if fu:
            fu["status"] = "cancelled"
        return fu or {"cancelled": False}

    def _message(self, channel: str, a: dict) -> dict:
        msg = {"id": _id("msg"), "lead_id": a["lead_id"], "channel": channel,
               "template": a.get("template", ""), "body": a.get("body", ""), "status": "sent"}
        self.store["messages"][msg["id"]] = msg
        return msg

    def _deal(self, a: dict) -> dict:
        deal = {"id": _id("deal"), "lead_id": a["lead_id"], "amount": a.get("amount", 0.0),
                "stage": "open"}
        self.store["deals"][deal["id"]] = deal
        bus.emit("deal.created", deal)
        return deal

    def _deal_update(self, a: dict) -> dict:
        deal = self.store["deals"].get(a.get("deal_id"))
        if deal:
            deal.update({k: v for k, v in a.items() if k != "deal_id"})
        return deal or {"updated": False}

    def _payment(self, a: dict) -> dict:
        pay = {"id": _id("pay"), "lead_id": a["lead_id"], "amount": a.get("amount", 0.0),
               "url": f"https://pay.local/{_id('lnk')}", "status": "pending"}
        self.store["payments"][pay["id"]] = pay
        return pay

    def _activity(self, lead_id: str, kind: str, body: str) -> dict:
        act = {"id": _id("act"), "lead_id": lead_id, "kind": kind, "body": body}
        self.store["activities"][act["id"]] = act
        return act

    def _transfer(self, a: dict) -> dict:
        h = {"id": _id("ho"), "lead_id": a["lead_id"], "context": a.get("context", {}),
             "status": "connected"}
        self.store["handoffs"][h["id"]] = h
        bus.emit("human.handoff", h)
        return h

    def _suppress(self, a: dict) -> dict:
        self.store["suppressions"][a["lead_id"]] = {"lead_id": a["lead_id"], "reason": a.get("reason", "opt_out")}
        lead = self.store["leads"].get(a["lead_id"])
        if lead:
            lead["suppressed"] = True
        bus.emit("lead.suppressed", {"lead_id": a["lead_id"]})
        return {"lead_id": a["lead_id"], "suppressed": True}

    # ---- extended capability implementations ------------------------------
    def _whatsapp(self, a: dict) -> dict:
        from ..business.whatsapp import whatsapp
        return whatsapp.send(a.get("to", a.get("lead_id", "")), text=a.get("body", a.get("text", "")),
                             template=a.get("template", ""), variables=a.get("variables"))

    def _recording_start(self, a: dict) -> dict:
        from ..telephony.recording import recordings
        return recordings.start(a.get("call_id", ""), consent=a.get("consent", True))

    def _recording_stop(self, a: dict) -> dict:
        from ..telephony.recording import recordings
        return recordings.stop(a.get("recording_id", ""))

    def _warm_transfer(self, a: dict) -> dict:
        from ..telephony.transfer import transfers
        return transfers.warm_transfer(a.get("call_id", ""), a.get("to", ""), a.get("context", {}))

    def _cold_transfer(self, a: dict) -> dict:
        from ..telephony.transfer import transfers
        return transfers.cold_transfer(a.get("call_id", ""), a.get("to", ""))

    def _conference(self, a: dict) -> dict:
        from ..telephony.transfer import transfers
        conf = transfers.conference(a.get("participants", []))
        return {"conference_id": conf.id, "participants": conf.participants, "status": conf.status}

    def _voicemail(self, a: dict) -> dict:
        from ..telephony.amd import voicemail
        return voicemail.drop_message(a.get("call_id", ""), a.get("message", ""))

    def _amd(self, a: dict) -> dict:
        from ..telephony.amd import voicemail
        return voicemail.on_answer(opening_transcript=a.get("opening_transcript", ""),
                                   greeting_ms=a.get("greeting_ms", 0),
                                   beep_detected=a.get("beep_detected", False)).as_dict()

    def _rag_search(self, a: dict) -> list[dict]:
        from ..ai.rag import store
        return store.search(a.get("query", ""), top_k=a.get("top_k"))

    def _mcp_call(self, a: dict) -> dict:
        from ..ai.mcp import client
        return client.call(a.get("name", ""), a.get("arguments", {}), server=a.get("server", "local"))
