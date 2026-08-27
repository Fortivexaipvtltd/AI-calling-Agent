from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from ..events import bus


def _id(p: str) -> str:
    return f"{p}_{uuid.uuid4().hex[:10]}"


@dataclass
class Conference:
    id: str = field(default_factory=lambda: _id("conf"))
    participants: list[str] = field(default_factory=list)
    status: str = "open"


class TransferService:
    """Warm transfer keeps the AI on the line to brief the human before the
    lead is connected; cold transfer hands off immediately. Conference bridges
    multiple legs (AI + human + lead)."""

    def __init__(self) -> None:
        self.conferences: dict[str, Conference] = {}
        self.transfers: dict[str, dict] = {}

    def warm_transfer(self, call_id: str, to: str, brief: dict) -> dict:
        conf = self._bridge([f"ai:{call_id}", f"human:{to}"])
        rec = {"id": _id("xfer"), "type": "warm", "call_id": call_id, "to": to,
               "conference_id": conf.id, "brief": brief, "stage": "briefing_human",
               "status": "connecting"}
        self.transfers[rec["id"]] = rec
        bus.emit("human.handoff", {"call_id": call_id, "type": "warm", "to": to})
        return rec

    def complete_warm(self, transfer_id: str, lead_leg: str) -> dict:
        rec = self.transfers.get(transfer_id)
        if not rec:
            return {"ok": False, "error": "unknown_transfer"}
        conf = self.conferences[rec["conference_id"]]
        conf.participants.append(lead_leg)
        rec.update(stage="lead_connected", status="completed")
        return {"ok": True, **rec}

    def cold_transfer(self, call_id: str, to: str) -> dict:
        rec = {"id": _id("xfer"), "type": "cold", "call_id": call_id, "to": to,
               "status": "transferred"}
        self.transfers[rec["id"]] = rec
        bus.emit("human.handoff", {"call_id": call_id, "type": "cold", "to": to})
        return rec

    def conference(self, participants: list[str]) -> Conference:
        return self._bridge(participants)

    def _bridge(self, participants: list[str]) -> Conference:
        conf = Conference(participants=list(participants))
        self.conferences[conf.id] = conf
        return conf


transfers = TransferService()
