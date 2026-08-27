from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

DURABLE_KEYS = {
    "goal",
    "occupation",
    "experience",
    "budget",
    "timeline",
    "preferences",
    "constraints",
    "decision_maker",
}


@dataclass
class Fact:
    key: str
    value: str
    source_call_id: str = ""
    confidence: float = 0.6
    at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SessionMemory:
    current_topic: str = ""
    current_intent: str = ""
    current_question: str = ""
    unresolved_point: str = ""


@dataclass
class SalesState:
    stage: str = "GREETING"
    score: int = 0
    close_probability: float = 0.0
    next_action: str = ""
    scheduled_followup: str = ""


class Memory:
    """Per-lead working + durable memory following the blueprint rules."""

    def __init__(self, call_id: str = "") -> None:
        self.call_id = call_id
        self.session = SessionMemory()
        self.sales = SalesState()
        self.facts: dict[str, Fact] = {}
        self.summaries: list[str] = []
        self.quotes: list[str] = []
        self.objections: list[str] = []
        self.commitments: list[str] = []

    def add_fact(self, key: str, value: str, confidence: float = 0.6) -> bool:
        """Rule: extract only durable facts; don't let a low-confidence
        extraction overwrite a trusted value."""
        if key not in DURABLE_KEYS:
            return False
        existing = self.facts.get(key)
        if existing and existing.confidence > confidence and existing.value != value:
            return False  # protect trusted data
        self.facts[key] = Fact(key, value, self.call_id, confidence)
        return True

    def correct_fact(self, key: str, value: str) -> None:
        """Lead corrections always win."""
        self.facts[key] = Fact(key, value, self.call_id, confidence=0.99)

    def relevant(self, state: str) -> dict[str, str]:
        """Retrieve only memories relevant to the current turn/state."""
        relevance = {
            "DISCOVERY": ["goal", "occupation", "experience"],
            "NEEDS_UNDERSTANDING": ["goal", "constraints", "timeline"],
            "QUALIFICATION": ["budget", "timeline", "decision_maker", "goal"],
            "OFFER": ["goal", "budget", "preferences"],
            "OBJECTION": ["budget", "constraints", "timeline"],
        }
        keys = relevance.get(state, list(self.facts.keys()))
        return {k: self.facts[k].value for k in keys if k in self.facts}

    def snapshot(self) -> dict:
        return {
            "session": self.session.__dict__,
            "sales": self.sales.__dict__,
            "facts": {k: v.value for k, v in self.facts.items()},
            "objections": list(self.objections),
            "commitments": list(self.commitments),
        }
