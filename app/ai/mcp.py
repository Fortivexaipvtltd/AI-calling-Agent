from __future__ import annotations

import json
import urllib.request

from ..config import settings
from ..tools.registry import ToolRegistry


class MCPClient:
    """Model Context Protocol client. Connects to MCP servers listed in
    `MCP_SERVERS`, lists their tools, and invokes them. When no servers are
    configured it exposes the built-in ToolRegistry as a local MCP server, so
    `mcp.call` always works and mirrors remote behaviour.
    """

    def __init__(self, servers: str | None = None, registry: ToolRegistry | None = None) -> None:
        self.servers = [s.strip() for s in (servers or settings.mcp_servers).split(",") if s.strip()]
        self.registry = registry or ToolRegistry()

    def list_tools(self) -> list[dict]:
        tools = [{"server": "local", "name": n} for n in self.registry.names()]
        for base in self.servers:
            try:
                tools += self._rpc(base, "tools/list", {}).get("tools", [])
            except Exception:
                continue
        return tools

    def call(self, name: str, arguments: dict, server: str = "local") -> dict:
        if server == "local":
            return self.registry.call(name, arguments)
        try:
            return self._rpc(server, "tools/call",
                             {"name": name, "arguments": arguments})
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _rpc(self, base: str, method: str, params: dict) -> dict:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                           "params": params}).encode()
        req = urllib.request.Request(base.rstrip("/") + "/rpc", data=body,
                                     headers={"content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        return data.get("result", data)


client = MCPClient()
