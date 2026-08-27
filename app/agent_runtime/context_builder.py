from __future__ import annotations

from .memory import Memory


def build_context(lead: dict, product: dict, memory: Memory, state: str, last_lead_text: str) -> dict:
    """Build only the relevant context for the current turn."""
    return {
        "lead": {"name": lead.get("name", ""), "stage": state, "score": memory.sales.score},
        "product": {
            "name": product.get("name", ""),
            "guarantee": product.get("guarantee", ""),
            "outcomes": product.get("outcomes", []),
        },
        "relevant_memory": memory.relevant(state),
        "objections": list(memory.objections),
        "last_lead_text": last_lead_text,
        "state": state,
    }
