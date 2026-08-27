from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LeadIn(BaseModel):
    name: str = ""
    phone: str = ""
    email: str = ""
    source: str = "import"


class LeadImport(BaseModel):
    leads: list[LeadIn]


class LeadOut(BaseModel):
    id: str
    name: str
    phone: str
    email: str
    status: str
    stage: str
    score: int
    close_probability: float
    suppressed: bool


class LeadPatch(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    status: str | None = None


class CampaignIn(BaseModel):
    name: str
    agent_id: str
    lead_ids: list[str] = Field(default_factory=list)


class AgentIn(BaseModel):
    name: str
    product_id: str
    playbook_id: str
    voice: str = "nova"
    persona: str = ""


class AgentPatch(BaseModel):
    name: str | None = None
    voice: str | None = None
    persona: str | None = None


class CallIn(BaseModel):
    lead_id: str
    agent_id: str


class TurnIn(BaseModel):
    text: str


class FollowupIn(BaseModel):
    lead_id: str
    reason: str = ""
    channel: str = "call"
    due_in_hours: int = 24


class CalendarCheck(BaseModel):
    lead_id: str
    day: str = "tomorrow"


class CalendarBook(BaseModel):
    lead_id: str
    slot: str


class SimulateIn(BaseModel):
    prospect: str = "interested_price_objection"
    agent_id: str | None = None


class Ok(BaseModel):
    ok: bool = True
    data: Any = None
