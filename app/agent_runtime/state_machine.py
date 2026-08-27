from __future__ import annotations

STATES = [
    "GREETING",
    "IDENTITY_CHECK",
    "DISCOVERY",
    "NEEDS_UNDERSTANDING",
    "QUALIFICATION",
    "OFFER",
    "OBJECTION",
    "RESOLVE",
    "NEXT_STEP_SELECTION",
    "CLOSE",
]

QUALIFICATION_BRANCHES = [
    "NOT_A_FIT",
    "NOT_INTERESTED",
    "NEEDS_TIME",
    "NEEDS_OTHER_DECISION_MAKER",
    "INTERESTED",
    "HOT",
]

NEXT_STEPS = [
    "BOOK_MEETING",
    "PAYMENT",
    "SEND_INFO",
    "FOLLOWUP",
    "HUMAN_HANDOFF",
    "CLOSE",
]

_LINEAR = {
    "GREETING": "IDENTITY_CHECK",
    "IDENTITY_CHECK": "DISCOVERY",
    "DISCOVERY": "NEEDS_UNDERSTANDING",
    "NEEDS_UNDERSTANDING": "QUALIFICATION",
    "QUALIFICATION": "OFFER",
    "OFFER": "OBJECTION",
    "OBJECTION": "RESOLVE",
    "RESOLVE": "NEXT_STEP_SELECTION",
    "NEXT_STEP_SELECTION": "CLOSE",
    "CLOSE": "CLOSE",
}


class StateMachine:
    def __init__(self, state: str = "GREETING") -> None:
        self.state = state if state in STATES else "GREETING"

    def advance(self) -> str:
        self.state = _LINEAR[self.state]
        return self.state

    def goto(self, state: str) -> str:
        if state in STATES:
            self.state = state
        return self.state

    def is_terminal(self) -> bool:
        return self.state == "CLOSE"
