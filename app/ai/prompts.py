from __future__ import annotations

from dataclasses import dataclass, field

from ..agent_runtime.memory import Memory


@dataclass
class PromptContext:
    persona: str = ""
    product: dict = field(default_factory=dict)
    state: str = "GREETING"
    facts: dict = field(default_factory=dict)
    objection: str = ""
    retrieved: str = ""
    rules: list[str] = field(default_factory=list)


# Instructions injected only when their condition is true (contextual instructions).
CONTEXTUAL_RULES = [
    (lambda c: c.objection == "price",
     "The lead raised price — reframe as investment + payment plan, cite the guarantee, never discount on the spot."),
    (lambda c: c.state == "QUALIFICATION",
     "You are qualifying — ask about timeline and budget, one question only."),
    (lambda c: bool(c.facts.get("timeline")),
     "They already told you their timeline — do not ask again; build on it."),
    (lambda c: c.state in ("OFFER", "RESOLVE"),
     "Tie the offer to a fact they shared earlier; be specific, not generic."),
]


class DynamicPromptBuilder:
    """Builds the system prompt fresh each turn from live state, memory and any
    retrieved context, and layers in only the contextual instructions that apply.
    This is what makes the agent adapt instead of using one static prompt."""

    def build(self, ctx: PromptContext) -> str:
        parts = [ctx.persona or "You are a warm, concise human sales counsellor on a live call."]
        if ctx.product:
            parts.append(
                f"APPROVED FACTS: product={ctx.product.get('name','')}; "
                f"outcomes={ctx.product.get('outcomes',[])}; "
                f"guarantee={ctx.product.get('guarantee','')}; "
                f"never_say={ctx.product.get('never_say',[])}.")
        if ctx.facts:
            parts.append(f"KNOWN ABOUT LEAD: {ctx.facts}.")
        if ctx.retrieved:
            parts.append(ctx.retrieved)
        for cond, instruction in CONTEXTUAL_RULES:
            try:
                if cond(ctx):
                    parts.append(instruction)
            except Exception:
                continue
        for rule in ctx.rules:
            parts.append(rule)
        parts.append("Reply in ONE short spoken sentence, ask at most one question.")
        return "\n".join(parts)

    def from_memory(self, persona: str, product: dict, memory: Memory,
                    state: str, retrieved: str = "") -> str:
        return self.build(PromptContext(
            persona=persona, product=product, state=state,
            facts={k: v.value for k, v in memory.facts.items()},
            objection=memory.objections[-1] if memory.objections else "",
            retrieved=retrieved))


builder = DynamicPromptBuilder()
