from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

EVENT_NAMES = [
    "lead.created",
    "lead.enriched",
    "lead.suppressed",
    "campaign.started",
    "call.started",
    "call.ended",
    "conversation.turn",
    "conversation.fact_extracted",
    "followup.created",
    "appointment.booked",
    "deal.created",
    "human.handoff",
]


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Callable]] = defaultdict(list)
        self.log: list[tuple[str, dict]] = []

    def subscribe(self, event: str, handler: Callable) -> None:
        self._subs[event].append(handler)

    def emit(self, event: str, payload: dict | None = None) -> None:
        payload = payload or {}
        self.log.append((event, payload))
        for handler in self._subs.get(event, []):
            handler(payload)


bus = EventBus()
