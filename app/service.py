from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .agent_runtime.runtime import AgentRuntime
from .conversation_worker.fact_extractor import extract_facts
from .conversation_worker.next_action import decide_next_action
from .models import (
    Agent,
    Call,
    CallInsight,
    Conversation,
    ConversationMessage,
    Followup,
    Lead,
    LeadFact,
    Product,
)
from .tools.registry import ToolRegistry


def persist_turn(db: Session, lead: Lead, rt) -> None:
    """Save all details after each turn: durable facts, stage, score, probability."""
    existing = {f.key: f for f in lead.facts}
    for key, fact in rt.memory.facts.items():
        row = existing.get(key)
        if row is None:
            db.add(LeadFact(lead_id=lead.id, key=key, value=fact.value,
                            source_call_id=rt.call_id, confidence=fact.confidence))
        elif row.value != fact.value and fact.confidence >= row.confidence:
            row.value, row.confidence, row.source_call_id = fact.value, fact.confidence, rt.call_id
    lead.stage = rt.sm.state
    lead.score = rt.memory.sales.score
    lead.close_probability = rt.memory.sales.close_probability
    db.flush()


def lead_to_dict(lead: Lead) -> dict:
    return {"id": lead.id, "name": lead.name, "phone": lead.phone,
            "email": lead.email, "suppressed": lead.suppressed}


def product_to_dict(product: Product) -> dict:
    return {"id": product.id, "name": product.name, "summary": product.summary,
            "outcomes": product.outcomes, "guarantee": product.guarantee,
            "faqs": product.faqs, "pricing_plans": product.pricing_plans,
            "never_say": product.never_say}


def build_runtime(db: Session, lead: Lead, agent: Agent) -> tuple[AgentRuntime, Call, ToolRegistry]:
    product = db.get(Product, agent.product_id)
    call = Call(org_id=lead.org_id, lead_id=lead.id, agent_id=agent.id, status="in_progress")
    db.add(call)
    db.flush()

    tools = ToolRegistry()
    tools.store["leads"][lead.id] = lead_to_dict(lead)
    tools.store["products"][product.id] = product_to_dict(product)

    rt = AgentRuntime(lead=lead_to_dict(lead), product=product_to_dict(product),
                      tools=tools, call_id=call.id, start_state=lead.stage or "GREETING")
    return rt, call, tools


def persist_conversation(db: Session, call: Call, rt: AgentRuntime) -> Conversation:
    conv = Conversation(call_id=call.id, lead_id=call.lead_id, state=rt.sm.state)
    db.add(conv)
    db.flush()
    for msg in rt.transcript():
        db.add(ConversationMessage(conversation_id=conv.id, role=msg["role"],
                                   text=msg["text"], state=msg.get("state", "")))
    return conv


def finalize_call(db: Session, call: Call, rt: AgentRuntime) -> CallInsight:
    transcript = rt.transcript()
    insights = extract_facts(transcript)
    action = decide_next_action(insights, rt.sm.state, rt.memory.sales.score)

    lead = db.get(Lead, call.lead_id)
    lead.stage = rt.sm.state
    lead.score = rt.memory.sales.score
    lead.close_probability = rt.memory.sales.close_probability
    lead.status = "closed" if rt.sm.is_terminal() else "in_progress"

    call.status = "completed"
    call.outcome = action

    ins = CallInsight(call_id=call.id, lead_id=call.lead_id, summary=insights["summary"],
                      sentiment=insights["sentiment"], objections=insights["objections"],
                      facts=insights["facts"], next_action=action)
    db.add(ins)

    # Automatic follow-up: schedule the next action unless the lead is done/suppressed.
    if not lead.suppressed and action not in ("human_call_now",):
        delay = {"followup_call_48h": 48, "book_meeting": 24,
                 "send_pricing_and_followup": 24, "nurture_email": 72,
                 "long_term_nurture": 168}.get(action, 48)
        channel = "email" if "email" in action or "pricing" in action or "nurture" in action else "call"
        db.add(Followup(org_id=lead.org_id, lead_id=lead.id, reason=action, channel=channel,
                        due_at=datetime.utcnow() + timedelta(hours=delay)))

    db.flush()
    return ins


# ---- durable live-call state (multi-instance / restart safe) -------------
def save_call_state(db: Session, rt: AgentRuntime, lead_id: str, agent_id: str,
                    active: bool = True) -> None:
    from .models import CallState
    row = db.get(CallState, rt.call_id)
    snap = rt.snapshot()
    if row is None:
        db.add(CallState(call_id=rt.call_id, lead_id=lead_id, agent_id=agent_id,
                         snapshot=snap, active=active))
    else:
        row.snapshot = snap
        row.active = active
    db.flush()


def load_runtime(db: Session, call_id: str) -> AgentRuntime | None:
    """Rehydrate a runtime from its durable snapshot. Returns None if unknown or
    already finished — the caller then treats the call as inactive."""
    from .models import Agent, CallState, Lead, Product
    row = db.get(CallState, call_id)
    if not row or not row.active:
        return None
    lead = db.get(Lead, row.lead_id)
    agent = db.get(Agent, row.agent_id) if row.agent_id else None
    product = db.get(Product, agent.product_id) if agent else None
    if not lead or not product:
        return None
    tools = ToolRegistry()
    tools.store["leads"][lead.id] = lead_to_dict(lead)
    tools.store["products"][product.id] = product_to_dict(product)
    return AgentRuntime.from_snapshot(lead=lead_to_dict(lead),
                                      product=product_to_dict(product),
                                      tools=tools, snapshot=row.snapshot)


def deactivate_call_state(db: Session, call_id: str) -> None:
    from .models import CallState
    row = db.get(CallState, call_id)
    if row:
        row.active = False
        db.flush()
