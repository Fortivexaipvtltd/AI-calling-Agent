from __future__ import annotations

from dataclasses import dataclass, field

from ..compliance import contains_opt_out
from ..tools.registry import ToolRegistry
from .conversation_policy import ConversationPolicy
from .handoff import build_handoff
from .memory import Memory
from .planner import Planner
from .repair_policy import RepairPolicy
from .responder import Responder
from .state_machine import StateMachine


@dataclass
class Turn:
    lead_text: str
    agent_text: str
    state: str
    tool_calls: list[dict] = field(default_factory=list)
    handoff: dict | None = None
    ended: bool = False


class AgentRuntime:
    """One conversation. Drives the state machine turn by turn."""

    def __init__(self, *, lead: dict, product: dict, tools: ToolRegistry,
                 call_id: str = "", start_state: str = "GREETING") -> None:
        self.lead = lead
        self.product = product
        self.tools = tools
        self.call_id = call_id
        self.sm = StateMachine(start_state)
        self.memory = Memory(call_id)
        self.memory.sales.stage = self.sm.state
        self.planner = Planner()
        self.responder = Responder()
        self.policy = ConversationPolicy()
        self.repair = RepairPolicy()
        self.turns: list[Turn] = []
        self._last_agent_line = ""

    def open(self) -> Turn:
        text = self.responder.generate(
            self.planner.plan(self.sm.state, "", self.memory, self.product),
            self.lead, self.product, self.memory, "", self.transcript(),
        )
        text = self.policy.apply(text)
        self._last_agent_line = text
        self.sm.advance()  # opener delivered; next lead turn is handled in IDENTITY_CHECK
        self.memory.sales.stage = self.sm.state
        turn = Turn(lead_text="", agent_text=text, state="GREETING")
        self.turns.append(turn)
        return turn

    def handle(self, lead_text: str) -> Turn:
        lead_text = (lead_text or "").strip()

        # Compliance: opt-out always wins.
        if contains_opt_out(lead_text):
            self.tools.call("compliance.suppress_lead", {"lead_id": self.lead["id"]})
            text = "Understood, I've removed you from our list. Sorry to bother you — take care."
            turn = Turn(lead_text=lead_text, agent_text=text, state="CLOSE",
                        tool_calls=[{"tool": "compliance.suppress_lead"}], ended=True)
            self.turns.append(turn)
            self.sm.goto("CLOSE")
            return turn

        # Repair before planning.
        repair_kind = self.repair.needs_repair(lead_text)
        if repair_kind:
            text = self.policy.apply(self.repair.repair_line(repair_kind, self._last_agent_line))
            self._last_agent_line = text
            turn = Turn(lead_text=lead_text, agent_text=text, state=self.sm.state)
            self.turns.append(turn)
            return turn

        # Ingest simple durable facts from what was actually said.
        self._extract_inline_facts(lead_text)

        plan = self.planner.plan(self.sm.state, lead_text, self.memory, self.product)
        tool_calls: list[dict] = []
        handoff = None
        agent_text = ""
        ended = False

        if plan.action == "handoff":
            handoff = build_handoff(self.lead, self.product, self.memory, lead_text)
            res = self.tools.call("human.transfer", {"lead_id": self.lead["id"], "context": handoff})
            tool_calls.append({"tool": "human.transfer", "result": res})
            agent_text = self.responder.closing_line("HUMAN_HANDOFF", self.lead)
            self.sm.goto("CLOSE")
            ended = True

        elif plan.action == "tool":
            args = dict(plan.tool_args or {})
            args["lead_id"] = self.lead["id"]
            res = self.tools.call(plan.tool, args)
            tool_calls.append({"tool": plan.tool, "args": args, "result": res})
            agent_text = self.responder.closing_line(plan.next_step or plan.intent, self.lead)
            self.memory.sales.next_action = plan.next_step
            self.sm.goto("CLOSE")
            ended = True

        elif plan.action == "end":
            agent_text = self.responder.closing_line("FOLLOWUP", self.lead)
            self.sm.goto("CLOSE")
            ended = True

        else:  # speak
            agent_text = self.responder.generate(plan, self.lead, self.product, self.memory,
                                                 lead_text, self.transcript())
            self.sm.advance()

        agent_text = self.policy.apply(agent_text)
        self._last_agent_line = agent_text
        self.memory.sales.stage = self.sm.state

        turn = Turn(lead_text=lead_text, agent_text=agent_text, state=self.sm.state,
                    tool_calls=tool_calls, handoff=handoff, ended=ended or self.sm.is_terminal())
        self.turns.append(turn)
        return turn

    def _extract_inline_facts(self, text: str) -> None:
        t = text.lower()
        if "job" in t or "career" in t or "become" in t or "want to" in t:
            self.memory.add_fact("goal", text, confidence=0.7)
        for token in text.replace(",", " ").split():
            digits = "".join(ch for ch in token if ch.isdigit())
            if digits and len(digits) >= 4:
                self.memory.add_fact("budget", token, confidence=0.7)
        if any(w in t for w in ("month", "week", "immediately", "asap", "soon")):
            self.memory.add_fact("timeline", text, confidence=0.65)
        if any(w in t for w in ("working", "student", "fresher", "engineer", "unemployed")):
            self.memory.add_fact("occupation", text, confidence=0.65)

    def transcript(self) -> list[dict]:
        out: list[dict] = []
        for t in self.turns:
            if t.lead_text:
                out.append({"role": "lead", "text": t.lead_text})
            if t.agent_text:
                out.append({"role": "agent", "text": t.agent_text, "state": t.state})
        return out

    # ---- durability -----------------------------------------------------
    def snapshot(self) -> dict:
        """Serialize enough state to resume this call on another worker or after
        a restart, without replaying tool side effects."""
        return {
            "call_id": self.call_id,
            "state": self.sm.state,
            "last_agent_line": self._last_agent_line,
            "turns": [{"lead_text": t.lead_text, "agent_text": t.agent_text,
                       "state": t.state, "ended": t.ended} for t in self.turns],
            "memory": {
                "facts": {k: {"value": f.value, "confidence": f.confidence,
                              "source_call_id": f.source_call_id}
                          for k, f in self.memory.facts.items()},
                "objections": list(self.memory.objections),
                "commitments": list(self.memory.commitments),
                "sales": {"stage": self.memory.sales.stage, "score": self.memory.sales.score,
                          "close_probability": self.memory.sales.close_probability,
                          "next_action": self.memory.sales.next_action},
            },
        }

    @classmethod
    def from_snapshot(cls, *, lead: dict, product: dict, tools: ToolRegistry,
                      snapshot: dict) -> AgentRuntime:
        from .memory import Fact
        rt = cls(lead=lead, product=product, tools=tools,
                 call_id=snapshot.get("call_id", ""),
                 start_state=snapshot.get("state", "GREETING"))
        rt._last_agent_line = snapshot.get("last_agent_line", "")
        rt.turns = [Turn(lead_text=t["lead_text"], agent_text=t["agent_text"],
                         state=t["state"], ended=t.get("ended", False))
                    for t in snapshot.get("turns", [])]
        mem = snapshot.get("memory", {})
        for k, f in mem.get("facts", {}).items():
            rt.memory.facts[k] = Fact(k, f["value"], f.get("source_call_id", ""),
                                      f.get("confidence", 0.6))
        rt.memory.objections = list(mem.get("objections", []))
        rt.memory.commitments = list(mem.get("commitments", []))
        s = mem.get("sales", {})
        rt.memory.sales.stage = s.get("stage", rt.sm.state)
        rt.memory.sales.score = s.get("score", 0)
        rt.memory.sales.close_probability = s.get("close_probability", 0.0)
        rt.memory.sales.next_action = s.get("next_action", "")
        return rt
