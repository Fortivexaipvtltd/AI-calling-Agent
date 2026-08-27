from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass


def _id(p: str) -> str:
    return f"{p}_{uuid.uuid4().hex[:10]}"


@dataclass
class SubAgent:
    name: str
    role: str                                   # qualifier | closer | support | scheduler
    # handle(message, blackboard) -> (reply, handoff_to or "")
    handle: Callable[[str, dict], tuple[str, str]]
    can_handle: Callable[[str, dict], bool] = lambda msg, bb: True


class Squad:
    """A team of specialist agents sharing a blackboard. One agent is active at a
    time; it may hand off to a teammate by name (agent->agent handoff) or escalate
    to a human. Deterministic routing keeps it testable without an LLM."""

    def __init__(self, agents: list[SubAgent], entry: str) -> None:
        self.id = _id("squad")
        self.agents = {a.name: a for a in agents}
        self.active = entry
        self.blackboard: dict = {}
        self.transcript: list[dict] = []

    def route(self, message: str) -> dict:
        agent = self.agents.get(self.active)
        if not agent:
            return {"error": "no_active_agent"}
        # If active can't handle, find a teammate who can.
        if not agent.can_handle(message, self.blackboard):
            for name, a in self.agents.items():
                if a.can_handle(message, self.blackboard):
                    self.active = name
                    agent = a
                    break
        reply, handoff = agent.handle(message, self.blackboard)
        self.transcript.append({"agent": agent.name, "role": agent.role,
                                "in": message, "out": reply, "handoff": handoff})
        if handoff and handoff in self.agents:
            self.active = handoff
        return {"agent": agent.name, "reply": reply, "handoff_to": handoff or None,
                "active": self.active}

    def run(self, messages: list[str]) -> dict:
        for m in messages:
            self.route(m)
        return {"squad": self.id, "active": self.active,
                "blackboard": self.blackboard, "transcript": self.transcript}


def default_squad() -> Squad:
    def qualifier(msg, bb):
        bb["qualified"] = any(w in msg.lower() for w in ("interested", "ready", "budget"))
        if bb["qualified"]:
            return ("Great, you sound like a strong fit — connecting you to enrolment.", "closer")
        return ("What's prompting you to look into this now?", "")

    def closer(msg, bb):
        if any(w in msg.lower() for w in ("pay", "enroll", "sign up")):
            bb["intent"] = "buy"
            return ("Perfect, I'll set up enrolment and scheduling.", "scheduler")
        return ("Here's how the programme is structured and priced.", "")

    def scheduler(msg, bb):
        bb["booked"] = True
        return ("Booked — you'll get a confirmation shortly.", "")

    return Squad([
        SubAgent("qualifier", "qualifier", qualifier),
        SubAgent("closer", "closer", closer,
                 can_handle=lambda m, bb: bb.get("qualified", False)),
        SubAgent("scheduler", "scheduler", scheduler,
                 can_handle=lambda m, bb: bb.get("intent") == "buy"),
    ], entry="qualifier")
