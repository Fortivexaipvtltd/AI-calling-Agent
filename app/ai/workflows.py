from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..tools.registry import ToolRegistry


@dataclass
class Step:
    name: str
    kind: str                      # tool | branch | transform | end
    tool: str = ""
    args: dict = field(default_factory=dict)
    # branch: predicate(context)->next step name; transform: fn(context)->dict
    predicate: Callable[[dict], str] | None = None
    transform: Callable[[dict], dict] | None = None
    next: str = ""


class Workflow:
    """Declarative multi-step automation over the tool registry. Steps read and
    write a shared context; branches pick the next step by predicate. This is the
    building block for reusable sequences (e.g. qualify -> book -> confirm)."""

    def __init__(self, name: str, steps: list[Step], start: str,
                 tools: ToolRegistry | None = None) -> None:
        self.id = f"wf_{uuid.uuid4().hex[:10]}"
        self.name = name
        self.steps = {s.name: s for s in steps}
        self.start = start
        self.tools = tools or ToolRegistry()

    def run(self, context: dict | None = None, max_steps: int = 50) -> dict:
        ctx: dict[str, Any] = dict(context or {})
        trace: list[dict] = []
        cur = self.start
        for _ in range(max_steps):
            step = self.steps.get(cur)
            if not step or step.kind == "end":
                break
            if step.kind == "tool":
                args = {**step.args, **{k: ctx[k] for k in ("lead_id",) if k in ctx}}
                res = self.tools.call(step.tool, args)
                ctx[step.name] = res.get("result", res)
                trace.append({"step": step.name, "tool": step.tool, "ok": res.get("ok")})
                cur = step.next
            elif step.kind == "transform" and step.transform:
                ctx.update(step.transform(ctx))
                trace.append({"step": step.name, "kind": "transform"})
                cur = step.next
            elif step.kind == "branch" and step.predicate:
                cur = step.predicate(ctx)
                trace.append({"step": step.name, "kind": "branch", "to": cur})
            else:
                break
        return {"workflow": self.name, "context": ctx, "trace": trace}


def sample_qualify_and_book(tools: ToolRegistry | None = None) -> Workflow:
    steps = [
        Step("check_perm", "tool", tool="compliance.check_call_permission", next="branch_ok"),
        Step("branch_ok", "branch",
             predicate=lambda c: "book" if c.get("check_perm", {}).get("allowed", True) else "stop"),
        Step("book", "tool", tool="calendar.book", args={"slot": "tomorrow 5pm"}, next="notify"),
        Step("notify", "tool", tool="message.send_sms",
             args={"template": "appointment_confirmation"}, next="done"),
        Step("stop", kind="end"),
        Step("done", kind="end"),
    ]
    return Workflow("qualify_and_book", steps, start="check_perm", tools=tools)
