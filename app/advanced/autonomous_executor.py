from __future__ import annotations

from dataclasses import dataclass, field

from ..tools.registry import ToolRegistry

# Goal -> ordered candidate tool steps. The executor runs them, observes results,
# and stops early on success or when a guardrail blocks. Deterministic locally.
GOAL_PLANS: dict[str, list[dict]] = {
    "enroll_lead": [
        {"tool": "compliance.check_call_permission", "gate": "allowed"},
        {"tool": "product.get_pricing"},
        {"tool": "payment.create_link"},
        {"tool": "message.send_sms", "args": {"template": "payment_link"}},
        {"tool": "crm.add_activity", "args": {"kind": "note", "body": "payment link sent"}},
    ],
    "book_meeting": [
        {"tool": "compliance.check_call_permission", "gate": "allowed"},
        {"tool": "calendar.check"},
        {"tool": "calendar.book", "args": {"slot": "tomorrow 5pm"}},
        {"tool": "message.send_email", "args": {"template": "appointment_confirmation"}},
    ],
    "nurture": [
        {"tool": "message.send_email", "args": {"template": "nurture_intro"}},
        {"tool": "followup.create", "args": {"reason": "nurture", "channel": "email",
                                             "due_in_hours": 72}},
    ],
}


@dataclass
class AutonomousExecutor:
    """Runs a goal to completion by executing steps, checking gates, and reacting
    to observations — the difference between 'call one tool' and 'get the job done'.
    Bounded by max_steps and by compliance gates so it can't run away."""

    tools: ToolRegistry = field(default_factory=ToolRegistry)
    max_steps: int = 12

    def run(self, goal: str, lead_id: str, context: dict | None = None) -> dict:
        plan = GOAL_PLANS.get(goal)
        if not plan:
            return {"goal": goal, "status": "unknown_goal",
                    "available": sorted(GOAL_PLANS)}
        ctx = dict(context or {})
        trace: list[dict] = []
        for step in plan[: self.max_steps]:
            args = {"lead_id": lead_id, **step.get("args", {})}
            res = self.tools.call(step["tool"], args)
            observation = res.get("result", res)
            trace.append({"tool": step["tool"], "ok": res.get("ok"),
                          "observation": observation})
            gate = step.get("gate")
            if gate and not (isinstance(observation, dict) and observation.get(gate, False)):
                return {"goal": goal, "status": "blocked", "at": step["tool"],
                        "reason": f"gate_failed:{gate}", "trace": trace}
            ctx[step["tool"]] = observation
        return {"goal": goal, "status": "completed", "steps": len(trace),
                "trace": trace, "context": ctx}
