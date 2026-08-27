from __future__ import annotations

from .memory import Memory


def build_handoff(lead: dict, product: dict, memory: Memory, last_transcript: str) -> dict:
    """Live context summary handed to a human before transfer."""
    facts = {k: v.value for k, v in memory.facts.items()}
    return {
        "lead": lead.get("name", "Unknown"),
        "course": product.get("name", ""),
        "stage": memory.sales.stage,
        "score": memory.sales.score,
        "goal": facts.get("goal", ""),
        "budget": facts.get("budget", ""),
        "interest": "High" if memory.sales.score >= 70 else "Medium",
        "objection": memory.objections[-1] if memory.objections else "",
        "previous_conversation": memory.summaries[-1] if memory.summaries else "",
        "recommended_action": "Speak with lead now"
        if memory.sales.score >= 80
        else "Follow up soon",
        "last_transcript": last_transcript,
    }


def should_handoff(memory: Memory, qualification: str) -> bool:
    return qualification == "HOT" or memory.sales.score >= 85
