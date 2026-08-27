from __future__ import annotations

from ..providers.llm import LLMResponder
from . import sales
from .memory import Memory
from .planner import Plan


class Responder:
    """Generates a short human response via the configured LLM provider.
    The provider handles natural phrasing; this class supplies the on-rails
    intent, approved facts and guardrails, and owns deterministic closers."""

    def __init__(self, provider: str | None = None) -> None:
        self.llm = LLMResponder(provider)

    def generate(self, plan: Plan, lead: dict, product: dict, memory: Memory,
                 lead_text: str, history: list[dict] | None = None) -> str:
        objection = memory.objections[-1] if memory.objections else sales.detect_objection(lead_text)
        facts = {k: v.value for k, v in memory.facts.items()}
        text = self.llm.word(
            intent=plan.intent, lead=lead, product=product, memory_facts=facts,
            objection=objection, lead_text=lead_text, history=history or [],
        )
        if plan.intent in ("discover", "clarify_need"):
            memory.session.current_question = text
        return text

    def closing_line(self, next_step: str, lead: dict) -> str:
        lines = {
            "PAYMENT": "Perfect — I've generated your secure payment link and texted it over.",
            "BOOK_MEETING": "Done — I've booked that slot and you'll get a confirmation shortly.",
            "SEND_INFO": "Sent — the details are on their way to your email now.",
            "FOLLOWUP": "Great — I'll follow up with you as agreed. Have a good day!",
            "HUMAN_HANDOFF": "You clearly know what you want — let me connect you to a specialist right now.",
            "NOT_INTERESTED": "No problem at all — thanks for your time, take care.",
            "NOT_A_FIT": "Appreciate your honesty — I'll send a couple of options that fit better.",
        }
        return lines.get(next_step, "Thanks for your time today!")
