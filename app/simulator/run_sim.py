from __future__ import annotations

from ..agent_runtime.runtime import AgentRuntime
from ..conversation_worker.fact_extractor import extract_facts
from ..conversation_worker.next_action import decide_next_action
from ..tools.registry import ToolRegistry
from .prospects import PROSPECTS

DEFAULT_LEAD = {"id": "lead_sim", "name": "Rahul Sharma", "phone": "+910000000000",
                "email": "rahul@example.com", "suppressed": False}

DEFAULT_PRODUCT = {
    "id": "prod_sim", "name": "Executive GenAI & Agentic AI Programme",
    "summary": "Applied AI programme for working professionals.",
    "outcomes": ["build real AI projects", "move into an AI-focused role"],
    "guarantee": "180-Day Better Offer Guarantee: continued support until a better offer "
                 "is secured, subject to T&C. Not an unconditional job guarantee.",
    "faqs": [], "pricing_plans": [{"name": "Full", "amount": 50000, "currency": "INR"}],
    "never_say": ["guaranteed job"],
}


def run(prospect: str = "interested_price_objection", lead: dict | None = None,
        product: dict | None = None, tools: ToolRegistry | None = None) -> dict:
    lead = lead or dict(DEFAULT_LEAD)
    product = product or dict(DEFAULT_PRODUCT)
    tools = tools or ToolRegistry()
    tools.store["leads"].setdefault(lead["id"], lead)
    tools.store["products"].setdefault(product["id"], product)

    script = PROSPECTS.get(prospect, PROSPECTS["interested_price_objection"])
    rt = AgentRuntime(lead=lead, product=product, tools=tools, call_id="call_sim")

    rt.open()
    for line in script:
        turn = rt.handle(line)
        if turn.ended:
            break

    transcript = rt.transcript()
    insights = extract_facts(transcript)
    action = decide_next_action(insights, rt.sm.state, rt.memory.sales.score)

    return {
        "prospect": prospect,
        "final_state": rt.sm.state,
        "score": rt.memory.sales.score,
        "close_probability": rt.memory.sales.close_probability,
        "insights": insights,
        "next_action": action,
        "memory": rt.memory.snapshot(),
        "transcript": transcript,
    }


def run_all() -> dict:
    return {name: run(name) for name in PROSPECTS}


if __name__ == "__main__":
    import json

    for name, result in run_all().items():
        print("=" * 70)
        print(f"PROSPECT: {name}  ->  state={result['final_state']} "
              f"score={result['score']} next={result['next_action']}")
        for m in result["transcript"]:
            who = "LEAD " if m["role"] == "lead" else "AGENT"
            print(f"  {who}: {m['text']}")
    print("=" * 70)
    print("summary:", json.dumps({k: v["final_state"] for k, v in run_all().items()}))
