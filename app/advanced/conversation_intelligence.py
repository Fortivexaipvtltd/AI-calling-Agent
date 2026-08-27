from __future__ import annotations

from dataclasses import dataclass, field

from ..agent_runtime import sales

_POSITIVE = ("interested", "great", "yes", "love", "perfect", "ready", "sounds good")
_NEGATIVE = ("not interested", "no", "busy", "stop", "expensive", "scam", "waste")
_BUYING = ("enroll", "sign up", "pay", "start", "how do i join", "when can i start")
_HESITATION = ("maybe", "not sure", "think about", "later", "discuss", "parents", "wife", "husband")


@dataclass
class Signals:
    sentiment: float = 0.0        # -1..1
    engagement: float = 0.5       # 0..1
    buying_intent: float = 0.0    # 0..1
    objection: str = ""
    risk: str = "none"            # none | churn | opt_out


@dataclass
class ConversationIntelligence:
    """Scores each lead turn in real time and recommends the next best action, so
    the agent adapts mid-call (push to close, slow down, address risk) instead of
    following a fixed script. Feeds the planner and the live dashboard."""

    turns: list[Signals] = field(default_factory=list)

    def observe(self, lead_text: str) -> Signals:
        t = (lead_text or "").lower()
        sig = Signals()
        pos = sum(w in t for w in _POSITIVE)
        neg = sum(w in t for w in _NEGATIVE)
        sig.sentiment = max(-1.0, min(1.0, (pos - neg) / 3.0))
        sig.buying_intent = min(1.0, sum(w in t for w in _BUYING) * 0.5)
        hesitation = sum(w in t for w in _HESITATION)
        sig.engagement = max(0.0, min(1.0, 0.5 + 0.2 * pos - 0.2 * hesitation))
        sig.objection = sales.detect_objection(t) or ""
        if any(w in t for w in ("stop calling", "remove me", "do not call")):
            sig.risk = "opt_out"
        elif sig.sentiment < -0.3 or hesitation >= 2:
            sig.risk = "churn"
        self.turns.append(sig)
        return sig

    def next_best_action(self) -> dict:
        if not self.turns:
            return {"action": "discover", "why": "no signal yet"}
        s = self.turns[-1]
        if s.risk == "opt_out":
            return {"action": "suppress_and_close", "why": "explicit opt-out"}
        if s.buying_intent >= 0.5:
            return {"action": "move_to_close", "why": "high buying intent"}
        if s.objection:
            return {"action": f"handle_objection:{s.objection}", "why": "open objection"}
        if s.risk == "churn":
            return {"action": "reduce_pressure", "why": "hesitation/negative sentiment"}
        if s.engagement >= 0.6:
            return {"action": "advance_stage", "why": "engaged"}
        return {"action": "re_engage", "why": "low engagement"}

    def trend(self) -> dict:
        if not self.turns:
            return {"turns": 0}
        n = len(self.turns)
        return {"turns": n,
                "avg_sentiment": round(sum(t.sentiment for t in self.turns) / n, 2),
                "avg_engagement": round(sum(t.engagement for t in self.turns) / n, 2),
                "peak_buying_intent": round(max(t.buying_intent for t in self.turns), 2),
                "risk": self.turns[-1].risk}
