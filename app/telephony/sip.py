from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from ..config import settings


def _id(p: str) -> str:
    return f"{p}_{uuid.uuid4().hex[:10]}"


@dataclass
class SIPTrunk:
    name: str
    host: str
    username: str = ""
    transport: str = "udp"  # udp | tcp | tls
    provider: str = "local"
    id: str = field(default_factory=lambda: _id("trunk"))
    registered: bool = False


class SIPGateway:
    """SIP signalling abstraction. `local` simulates REGISTER/INVITE so the
    stack runs offline; real trunks (twilio_sip, telnyx) drop in unchanged."""

    def __init__(self, provider: str | None = None) -> None:
        self.provider = provider or settings.sip_provider
        self.trunks: dict[str, SIPTrunk] = {}

    def create_trunk(self, name: str, host: str, username: str = "",
                     transport: str = "udp") -> SIPTrunk:
        trunk = SIPTrunk(name=name, host=host, username=username,
                         transport=transport, provider=self.provider)
        self.trunks[trunk.id] = trunk
        return trunk

    def register(self, trunk_id: str) -> dict:
        trunk = self.trunks.get(trunk_id)
        if not trunk:
            return {"ok": False, "error": "unknown_trunk"}
        trunk.registered = True
        return {"ok": True, "trunk_id": trunk_id, "status": "registered",
                "contact": f"sip:{trunk.username or 'agent'}@{trunk.host}"}

    def invite(self, trunk_id: str, uri: str) -> dict:
        """Place a SIP INVITE (outbound over the trunk)."""
        trunk = self.trunks.get(trunk_id)
        if not trunk or not trunk.registered:
            return {"provider": self.provider, "status": "failed", "error": "trunk_not_registered"}
        return {"provider": self.provider, "status": "ringing",
                "sip_call_id": f"{_id('sip')}@{settings.sip_domain}", "uri": uri}


gateway = SIPGateway()
