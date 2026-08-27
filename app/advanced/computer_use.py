from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field

from ..tools.registry import ToolRegistry

# Allowlisted computer/browser actions the agent may take. A virtual screen state
# makes this runnable and testable offline; a real driver (Playwright/computer-use
# API) implements the same verbs behind `_perform`.
ALLOWED_ACTIONS = {"navigate", "click", "type", "read", "screenshot", "http_get", "http_post"}


@dataclass
class VirtualScreen:
    url: str = "about:blank"
    fields: dict = field(default_factory=dict)
    log: list[str] = field(default_factory=list)


class ComputerUse:
    """Lets the agent operate software: fill a CRM form, click through a portal,
    or call an arbitrary HTTP API — alongside the structured ToolRegistry. Every
    action is allowlisted and logged; destructive verbs are simply not exposed."""

    def __init__(self, tools: ToolRegistry | None = None,
                 allow_network: bool = False) -> None:
        self.tools = tools or ToolRegistry()
        self.allow_network = allow_network
        self.screen = VirtualScreen()

    def run(self, actions: list[dict]) -> dict:
        results = []
        for action in actions:
            verb = action.get("action")
            if verb not in ALLOWED_ACTIONS:
                results.append({"action": verb, "ok": False, "error": "not_allowed"})
                continue
            results.append(self._perform(verb, action))
        return {"steps": len(results), "results": results,
                "screen": {"url": self.screen.url, "fields": self.screen.fields}}

    def _perform(self, verb: str, action: dict) -> dict:
        if verb == "navigate":
            self.screen.url = action.get("url", "about:blank")
            self.screen.log.append(f"navigate {self.screen.url}")
            return {"action": verb, "ok": True, "url": self.screen.url}
        if verb == "type":
            self.screen.fields[action.get("field", "")] = action.get("text", "")
            return {"action": verb, "ok": True, "field": action.get("field")}
        if verb == "click":
            self.screen.log.append(f"click {action.get('target','')}")
            return {"action": verb, "ok": True, "target": action.get("target")}
        if verb == "read":
            return {"action": verb, "ok": True,
                    "value": self.screen.fields.get(action.get("field", ""), "")}
        if verb == "screenshot":
            return {"action": verb, "ok": True, "state": dict(self.screen.fields)}
        if verb in ("http_get", "http_post"):
            return self._http(verb, action)
        return {"action": verb, "ok": False, "error": "unhandled"}

    def _http(self, verb: str, action: dict) -> dict:
        if not self.allow_network:
            return {"action": verb, "ok": False, "error": "network_disabled",
                    "would_call": action.get("url")}
        try:
            data = json.dumps(action.get("body", {})).encode() if verb == "http_post" else None
            req = urllib.request.Request(action["url"], data=data,
                                         method="POST" if verb == "http_post" else "GET",
                                         headers=action.get("headers", {}))
            with urllib.request.urlopen(req, timeout=15) as resp:
                return {"action": verb, "ok": True, "status": resp.status,
                        "body": resp.read(2000).decode("utf-8", "ignore")}
        except Exception as exc:
            return {"action": verb, "ok": False, "error": str(exc)}
