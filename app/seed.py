from __future__ import annotations

from sqlalchemy import select

from .config import settings
from .db import SessionLocal
from .models import Agent, Lead, Organization, Playbook, Product


def seed() -> dict:
    db = SessionLocal()
    try:
        org = db.get(Organization, settings.default_org_id)
        if not org:
            org = Organization(id=settings.default_org_id, name="Empowers Academy")
            db.add(org)
            db.flush()

        product = db.scalar(select(Product).where(Product.org_id == org.id))
        if not product:
            product = Product(
                org_id=org.id,
                name="Executive GenAI & Agentic AI Programme",
                summary="Applied programme for working professionals moving into AI roles.",
                outcomes=["build real AI projects", "move into an AI-focused role", "mentored learning"],
                eligibility={"min_experience_years": 0},
                guarantee=(
                    "180-Day Better Offer Guarantee: continued support until a better offer "
                    "is secured, subject to terms and conditions. Not an unconditional job guarantee."
                ),
                faqs=[
                    {"q": "is there a job guarantee", "a": "It is continued support until a better "
                     "offer is secured, subject to T&C — not an unconditional job guarantee."},
                    {"q": "how long is the programme", "a": "Designed around working schedules over "
                     "several months with mentor support."},
                ],
                pricing_plans=[
                    {"name": "Full", "amount": 50000, "currency": "INR"},
                    {"name": "EMI", "amount": 50000, "currency": "INR", "installments": 6},
                ],
                never_say=["guaranteed job", "assured placement", "100% job"],
            )
            db.add(product)
            db.flush()

        playbook = db.scalar(select(Playbook).where(Playbook.org_id == org.id))
        if not playbook:
            playbook = Playbook(
                org_id=org.id,
                product_id=product.id,
                discovery_questions=[
                    "What's prompting you to look at this right now?",
                    "What would success look like in the next few months?",
                ],
                qualification_questions=[
                    "What timeline are you working with?",
                    "Have you set aside a budget for this?",
                ],
                objection_rules=[
                    {"name": "price", "approach": "reframe as investment + plan + guarantee"},
                    {"name": "trust", "approach": "offer written approved details"},
                ],
            )
            db.add(playbook)
            db.flush()

        agent = db.scalar(select(Agent).where(Agent.org_id == org.id))
        if not agent:
            agent = Agent(
                org_id=org.id, name="Highh Human Agent", product_id=product.id,
                playbook_id=playbook.id, voice="nova",
                persona="Warm, concise admissions counsellor. One question at a time.",
            )
            db.add(agent)
            db.flush()

        if not db.scalar(select(Lead).where(Lead.org_id == org.id)):
            for n, ph in [("Rahul Sharma", "+919000000001"), ("Anita Rao", "+919000000002")]:
                db.add(Lead(org_id=org.id, name=n, phone=ph, source="seed"))

        db.commit()
        return {"org_id": org.id, "product_id": product.id,
                "playbook_id": playbook.id, "agent_id": agent.id}
    finally:
        db.close()
