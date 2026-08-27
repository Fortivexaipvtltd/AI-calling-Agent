from __future__ import annotations

import heapq
import itertools
import uuid
from dataclasses import dataclass, field


def _id(p: str) -> str:
    return f"{p}_{uuid.uuid4().hex[:10]}"


@dataclass(order=True)
class _Entry:
    priority: int
    seq: int
    call_id: str = field(compare=False)


@dataclass
class CallQueue:
    name: str
    id: str = field(default_factory=lambda: _id("q"))
    _heap: list = field(default_factory=list)
    _counter: object = field(default_factory=lambda: itertools.count())
    agents: list[str] = field(default_factory=list)
    busy: set = field(default_factory=set)

    def enqueue(self, call_id: str, priority: int = 5) -> dict:
        # lower priority value = served first
        heapq.heappush(self._heap, _Entry(priority, next(self._counter), call_id))
        return {"queue": self.id, "call_id": call_id, "position": len(self._heap)}

    def dequeue(self) -> str | None:
        return heapq.heappop(self._heap).call_id if self._heap else None

    def register_agent(self, agent_id: str) -> None:
        if agent_id not in self.agents:
            self.agents.append(agent_id)

    def assign(self) -> dict | None:
        free = [a for a in self.agents if a not in self.busy]
        if not free or not self._heap:
            return None
        call_id = self.dequeue()
        agent_id = free[0]
        self.busy.add(agent_id)
        return {"call_id": call_id, "agent_id": agent_id}

    def release_agent(self, agent_id: str) -> None:
        self.busy.discard(agent_id)

    def depth(self) -> int:
        return len(self._heap)


class QueueService:
    def __init__(self) -> None:
        self.queues: dict[str, CallQueue] = {}

    def create(self, name: str) -> CallQueue:
        q = CallQueue(name=name)
        self.queues[q.id] = q
        return q


queues = QueueService()
