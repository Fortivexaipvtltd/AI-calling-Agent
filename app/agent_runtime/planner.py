from __future__ import annotations

from dataclasses import dataclass

from . import sales
from .handoff import should_handoff
from .memory import Memory


@dataclass
class Plan:
    state: str
    action: str  # speak | tool | handoff | end
    intent: str = ""
    tool: str = ""
    tool_args: dict | None = None
    next_step: str = ""


class Planner:
    """Decide next action / tool / state for the current turn."""

    def plan(self, state: str, lead_text: str, memory: Memory, product: dict) -> Plan:
        objection = sales.detect_objection(lead_text)
        if objection:
            memory.objections.append(objection)

        # Disengagement can happen at any state, not only QUALIFICATION.
        if lead_text:
            dis = sales.disengagement(lead_text)
            if dis == "NOT_INTERESTED":
                return Plan(state=state, action="tool", intent="NOT_INTERESTED",
                            tool="followup.create",
                            tool_args={"reason": "not_interested", "channel": "email"},
                            next_step="NOT_INTERESTED")
            if dis == "NEEDS_OTHER_DECISION_MAKER":
                return Plan(state=state, action="tool", intent="NEEDS_OTHER_DECISION_MAKER",
                            tool="message.send_email",
                            tool_args={"template": "summary_for_decision_maker"},
                            next_step="SEND_INFO")
            if dis == "NEEDS_TIME":
                return Plan(state=state, action="tool", intent="NEEDS_TIME",
                            tool="followup.create",
                            tool_args={"reason": "needs_time", "channel": "call", "due_in_hours": 168},
                            next_step="FOLLOWUP")

        if state == "GREETING":
            return Plan(state=state, action="speak", intent="greet")

        if state == "IDENTITY_CHECK":
            return Plan(state=state, action="speak", intent="identity")

        if state == "DISCOVERY":
            return Plan(state=state, action="speak", intent="discover")

        if state == "NEEDS_UNDERSTANDING":
            return Plan(state=state, action="speak", intent="clarify_need")

        if state == "QUALIFICATION":
            q = sales.classify_qualification(lead_text, memory)
            score, prob = sales.score_lead(memory, q)
            memory.sales.score, memory.sales.close_probability = score, prob
            if q in ("NOT_INTERESTED", "NOT_A_FIT"):
                return Plan(state=state, action="tool", intent=q, tool="followup.create",
                            tool_args={"reason": q, "channel": "email"}, next_step="FOLLOWUP")
            if should_handoff(memory, q):
                return Plan(state=state, action="handoff", intent=q, next_step="HUMAN_HANDOFF")
            return Plan(state=state, action="speak", intent=q)

        if state == "OFFER":
            return Plan(state=state, action="speak", intent="offer")

        if state == "OBJECTION":
            return Plan(state=state, action="speak", intent="objection")

        if state == "RESOLVE":
            if should_handoff(memory, "INTERESTED"):
                return Plan(state=state, action="handoff", next_step="HUMAN_HANDOFF")
            return Plan(state=state, action="speak", intent="resolve")

        if state == "NEXT_STEP_SELECTION":
            return self._next_step(lead_text, memory)

        return Plan(state=state, action="end", intent="close")

    def _next_step(self, lead_text: str, memory: Memory) -> Plan:
        t = lead_text.lower()
        if any(w in t for w in ("pay", "enroll", "sign up", "buy")):
            return Plan(state="NEXT_STEP_SELECTION", action="tool", intent="payment",
                        tool="payment.create_link", tool_args={}, next_step="PAYMENT")
        if any(w in t for w in ("meeting", "call back", "demo", "talk to")):
            return Plan(state="NEXT_STEP_SELECTION", action="tool", intent="book",
                        tool="calendar.book", tool_args={"slot": "tomorrow 5pm"},
                        next_step="BOOK_MEETING")
        if any(w in t for w in ("email", "send", "details", "brochure", "info")):
            return Plan(state="NEXT_STEP_SELECTION", action="tool", intent="send_info",
                        tool="message.send_email", tool_args={"template": "program_details"},
                        next_step="SEND_INFO")
        return Plan(state="NEXT_STEP_SELECTION", action="tool", intent="followup",
                    tool="followup.create", tool_args={"reason": "warm", "channel": "call"},
                    next_step="FOLLOWUP")
