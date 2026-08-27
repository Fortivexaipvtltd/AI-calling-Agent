from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


def _id(p: str) -> str:
    return f"{p}_{uuid.uuid4().hex[:8]}"


@dataclass
class Worker:
    name: str
    kind: str                       # ai | human
    skills: set = field(default_factory=set)
    capacity: int = 1               # concurrent tasks
    load: int = 0
    id: str = field(default_factory=lambda: _id("wrk"))

    def available_for(self, skill: str) -> bool:
        return skill in self.skills and self.load < self.capacity


@dataclass
class Task:
    kind: str                       # cold_call | close | escalation | support | followup
    lead_id: str
    priority: int = 5
    id: str = field(default_factory=lambda: _id("task"))
    assigned_to: str = ""
    status: str = "queued"


# Which worker kind should own each task type by default (AI handles volume,
# humans handle high-value / sensitive work). Routing can still override by skill.
DEFAULT_OWNER = {"cold_call": "ai", "followup": "ai", "support": "ai",
                 "close": "human", "escalation": "human"}


class Workforce:
    """Orchestrates a mixed AI + human team. Routes each task to the best-fit,
    least-loaded worker by skill and policy, escalates AI -> human when needed,
    and tracks load so nobody is overwhelmed."""

    def __init__(self) -> None:
        self.workers: dict[str, Worker] = {}
        self.tasks: dict[str, Task] = {}
        self.assignments: list[dict] = []

    def add_worker(self, name: str, kind: str, skills: list[str],
                   capacity: int = 1) -> Worker:
        w = Worker(name=name, kind=kind, skills=set(skills), capacity=capacity)
        self.workers[w.id] = w
        return w

    def submit(self, kind: str, lead_id: str, priority: int = 5) -> dict:
        task = Task(kind=kind, lead_id=lead_id, priority=priority)
        self.tasks[task.id] = task
        return self._assign(task)

    def _assign(self, task: Task) -> dict:
        preferred = DEFAULT_OWNER.get(task.kind, "ai")
        candidates = [w for w in self.workers.values() if w.available_for(task.kind)]
        # prefer the policy owner kind, then least loaded
        candidates.sort(key=lambda w: (w.kind != preferred, w.load))
        if not candidates:
            task.status = "unassigned"
            return {"task_id": task.id, "status": "unassigned",
                    "reason": "no_available_worker"}
        w = candidates[0]
        w.load += 1
        task.assigned_to = w.id
        task.status = "assigned"
        rec = {"task_id": task.id, "kind": task.kind, "worker": w.name,
               "worker_kind": w.kind, "at": datetime.utcnow().isoformat()}
        self.assignments.append(rec)
        return rec

    def escalate(self, task_id: str) -> dict:
        task = self.tasks.get(task_id)
        if not task:
            return {"ok": False, "error": "unknown_task"}
        old = self.workers.get(task.assigned_to)
        if old:
            old.load = max(0, old.load - 1)
        task.kind = "escalation"
        return {"ok": True, **self._assign(task)}

    def complete(self, task_id: str) -> dict:
        task = self.tasks.get(task_id)
        if not task:
            return {"ok": False, "error": "unknown_task"}
        w = self.workers.get(task.assigned_to)
        if w:
            w.load = max(0, w.load - 1)
        task.status = "done"
        return {"ok": True, "task_id": task_id, "status": "done"}

    def utilization(self) -> dict:
        return {w.name: {"kind": w.kind, "load": w.load, "capacity": w.capacity}
                for w in self.workers.values()}


workforce = Workforce()
