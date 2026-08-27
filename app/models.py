from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def now() -> datetime:
    return datetime.utcnow()


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("org"))
    name: Mapped[str] = mapped_column(String, default="Default Org")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("usr"))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    email: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String, default="")
    role: Mapped[str] = mapped_column(String, default="agent")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("prod"))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String)
    summary: Mapped[str] = mapped_column(Text, default="")
    outcomes: Mapped[dict] = mapped_column(JSON, default=list)
    eligibility: Mapped[dict] = mapped_column(JSON, default=dict)
    guarantee: Mapped[str] = mapped_column(Text, default="")
    faqs: Mapped[dict] = mapped_column(JSON, default=list)
    pricing_plans: Mapped[dict] = mapped_column(JSON, default=list)
    never_say: Mapped[dict] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Playbook(Base):
    __tablename__ = "sales_playbooks"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("pb"))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    discovery_questions: Mapped[dict] = mapped_column(JSON, default=list)
    qualification_questions: Mapped[dict] = mapped_column(JSON, default=list)
    objection_rules: Mapped[dict] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("agt"))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    playbook_id: Mapped[str] = mapped_column(ForeignKey("sales_playbooks.id"))
    voice: Mapped[str] = mapped_column(String, default="nova")
    persona: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Lead(Base):
    __tablename__ = "leads"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("lead"))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String, default="")
    phone: Mapped[str] = mapped_column(String, default="")
    email: Mapped[str] = mapped_column(String, default="")
    source: Mapped[str] = mapped_column(String, default="import")
    status: Mapped[str] = mapped_column(String, default="new")
    stage: Mapped[str] = mapped_column(String, default="GREETING")
    score: Mapped[int] = mapped_column(Integer, default=0)
    close_probability: Mapped[float] = mapped_column(Float, default=0.0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    suppressed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    facts: Mapped[list[LeadFact]] = relationship(back_populates="lead", cascade="all, delete-orphan")


class LeadFact(Base):
    __tablename__ = "lead_facts"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("fact"))
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    key: Mapped[str] = mapped_column(String)
    value: Mapped[str] = mapped_column(Text)
    source_call_id: Mapped[str] = mapped_column(String, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.6)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    lead: Mapped[Lead] = relationship(back_populates="facts")


class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("camp"))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    status: Mapped[str] = mapped_column(String, default="draft")
    lead_ids: Mapped[dict] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Call(Base):
    __tablename__ = "calls"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("call"))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    status: Mapped[str] = mapped_column(String, default="initiated")
    outcome: Mapped[str] = mapped_column(String, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("conv"))
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id"))
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    state: Mapped[str] = mapped_column(String, default="GREETING")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("msg"))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String)  # lead | agent
    text: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class CallInsight(Base):
    __tablename__ = "call_insights"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("ins"))
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id"))
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    summary: Mapped[str] = mapped_column(Text, default="")
    sentiment: Mapped[str] = mapped_column(String, default="neutral")
    objections: Mapped[dict] = mapped_column(JSON, default=list)
    facts: Mapped[dict] = mapped_column(JSON, default=dict)
    next_action: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Followup(Base):
    __tablename__ = "followups"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("fu"))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    due_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    reason: Mapped[str] = mapped_column(String, default="")
    channel: Mapped[str] = mapped_column(String, default="call")
    status: Mapped[str] = mapped_column(String, default="scheduled")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Appointment(Base):
    __tablename__ = "appointments"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("appt"))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    slot: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="booked")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Deal(Base):
    __tablename__ = "deals"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("deal"))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    stage: Mapped[str] = mapped_column(String, default="open")
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Activity(Base):
    __tablename__ = "activities"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("act"))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    kind: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Suppression(Base):
    __tablename__ = "lead_suppressions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("sup"))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    reason: Mapped[str] = mapped_column(String, default="opt_out")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("aud"))
    org_id: Mapped[str] = mapped_column(String, default="")
    actor: Mapped[str] = mapped_column(String, default="system")
    action: Mapped[str] = mapped_column(String)
    target: Mapped[str] = mapped_column(String, default="")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ApiKey(Base):
    """Hashed API credential. The raw key is shown once at creation and never
    stored; only its SHA-256 hash is persisted, so a DB leak can't be replayed."""

    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("key"))
    org_id: Mapped[str] = mapped_column(String, default="")
    name: Mapped[str] = mapped_column(String, default="")
    prefix: Mapped[str] = mapped_column(String, default="")        # first 8 chars, for display
    key_hash: Mapped[str] = mapped_column(String, index=True)
    role: Mapped[str] = mapped_column(String, default="admin")
    active: Mapped[bool] = mapped_column(default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class UsageRecordRow(Base):
    """Durable usage ledger for metered billing (survives restarts)."""

    __tablename__ = "usage_records"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: _id("use"))
    org_id: Mapped[str] = mapped_column(String, index=True, default="")
    metric: Mapped[str] = mapped_column(String, index=True)
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class CallState(Base):
    """Durable snapshot of an in-progress call so a live conversation survives a
    restart and can be resumed by any worker (multi-instance safe)."""

    __tablename__ = "call_states"
    call_id: Mapped[str] = mapped_column(String, primary_key=True)
    lead_id: Mapped[str] = mapped_column(String, index=True)
    agent_id: Mapped[str] = mapped_column(String, default="")
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
