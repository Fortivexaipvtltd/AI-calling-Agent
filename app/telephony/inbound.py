from __future__ import annotations

from ..events import bus
from .ivr import DEFAULT_MENU, IVR
from .queues import queues


class InboundRouter:
    """Handles calls that come *to* the platform (the mirror of outbound).

    Looks up the caller, optionally runs an IVR, and either answers with an AI
    agent or drops the call into a queue for a human. Telephony webhooks call
    `handle`; the local engine makes this fully testable offline.
    """

    def __init__(self) -> None:
        self.ivr = IVR(DEFAULT_MENU)

    def handle(self, *, from_number: str, to_number: str, call_id: str,
               digits: list[str] | None = None) -> dict:
        bus.emit("call.started", {"call_id": call_id, "direction": "inbound",
                                  "from": from_number, "to": to_number})
        if digits:
            result = self.ivr.run(digits)
            if result.get("status") == "action":
                return self._route_action(result["action"], call_id, from_number)
            return {"call_id": call_id, "next": "ivr", **result}
        return {"call_id": call_id, "next": "answer_ai",
                "agent": "greet", "from": from_number, "to": to_number}

    def _route_action(self, action: str, call_id: str, from_number: str) -> dict:
        if action == "human_agent":
            q = next(iter(queues.queues.values()), None) or queues.create("inbound")
            pos = q.enqueue(call_id, priority=3)
            return {"call_id": call_id, "next": "queue", **pos}
        return {"call_id": call_id, "next": "answer_ai", "route": action}


inbound = InboundRouter()
