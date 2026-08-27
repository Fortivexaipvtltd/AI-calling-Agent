from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class IVRNode:
    prompt: str
    # digit -> next node key OR terminal action string ("action:transfer")
    choices: dict[str, str] = field(default_factory=dict)


class DTMFDecoder:
    """Collects DTMF key presses into a buffer; # submits, * clears."""

    def __init__(self) -> None:
        self.buffer: list[str] = []

    def press(self, digit: str) -> dict:
        digit = str(digit)[:1]
        if digit == "#":
            value = "".join(self.buffer)
            self.buffer.clear()
            return {"event": "submit", "value": value}
        if digit == "*":
            self.buffer.clear()
            return {"event": "clear", "value": ""}
        if digit.isdigit():
            self.buffer.append(digit)
        return {"event": "digit", "value": "".join(self.buffer)}


class IVR:
    """Small deterministic IVR runner. Walks a menu tree from DTMF input and
    stops at the first terminal action (e.g. route to a queue or an agent)."""

    def __init__(self, menu: dict[str, IVRNode], start: str = "root") -> None:
        self.menu = menu
        self.start = start

    def run(self, digits: list[str]) -> dict:
        node_key = self.start
        path = [node_key]
        for d in digits:
            node = self.menu.get(node_key)
            if not node:
                break
            nxt = node.choices.get(str(d))
            if not nxt:
                return {"status": "invalid", "at": node_key, "path": path,
                        "prompt": node.prompt}
            if nxt.startswith("action:"):
                path.append(nxt)
                return {"status": "action", "action": nxt.split(":", 1)[1], "path": path}
            node_key = nxt
            path.append(node_key)
        node = self.menu.get(node_key)
        return {"status": "prompt", "at": node_key, "path": path,
                "prompt": node.prompt if node else ""}


DEFAULT_MENU = {
    "root": IVRNode("Press 1 for admissions, 2 for support, 0 for an agent.",
                    {"1": "admissions", "2": "support", "0": "action:human_agent"}),
    "admissions": IVRNode("Press 1 for GenAI programme, 2 for Business & AI.",
                          {"1": "action:route_genai", "2": "action:route_business"}),
    "support": IVRNode("Press 1 for payments, 2 for schedule.",
                       {"1": "action:route_payments", "2": "action:route_schedule"}),
}
