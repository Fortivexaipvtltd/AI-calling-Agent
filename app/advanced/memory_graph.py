from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime


def _id(p: str) -> str:
    return f"{p}_{uuid.uuid4().hex[:8]}"


@dataclass
class Node:
    kind: str                 # lead | org | product | objection | goal | agent | deal
    key: str                  # natural key (e.g. lead_id, "price")
    props: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: _id("n"))


@dataclass
class Edge:
    src: str
    rel: str                  # has_goal | raised | interested_in | employed_at | owns
    dst: str
    props: dict = field(default_factory=dict)
    at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class MemoryGraph:
    """A durable graph across calls and leads — not just per-call facts. Lets the
    system answer relational questions ('which leads raised price and want an AI
    job in <3 months') and carry context between conversations."""

    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self._by_key: dict[tuple[str, str], str] = {}
        self._out: dict[str, list[Edge]] = defaultdict(list)

    def upsert(self, kind: str, key: str, **props) -> Node:
        node_id = self._by_key.get((kind, key))
        if node_id:
            self.nodes[node_id].props.update(props)
            return self.nodes[node_id]
        node = Node(kind=kind, key=key, props=props)
        self.nodes[node.id] = node
        self._by_key[(kind, key)] = node.id
        return node

    def relate(self, src: Node, rel: str, dst: Node, **props) -> Edge:
        edge = Edge(src=src.id, rel=rel, dst=dst.id, props=props)
        self.edges.append(edge)
        self._out[src.id].append(edge)
        return edge

    def ingest_lead_memory(self, lead_id: str, lead_name: str, facts: dict,
                           objections: list[str]) -> Node:
        """Fold a call's per-lead memory into the durable graph."""
        lead = self.upsert("lead", lead_id, name=lead_name)
        for key, value in facts.items():
            fnode = self.upsert(key, str(value))
            self.relate(lead, f"has_{key}", fnode)
        for obj in objections:
            onode = self.upsert("objection", obj)
            self.relate(lead, "raised", onode)
        return lead

    def neighbors(self, kind: str, key: str) -> list[dict]:
        node_id = self._by_key.get((kind, key))
        if not node_id:
            return []
        return [{"rel": e.rel, "kind": self.nodes[e.dst].kind,
                 "key": self.nodes[e.dst].key} for e in self._out[node_id]]

    def leads_with(self, rel: str, dst_kind: str, dst_key: str) -> list[str]:
        dst_id = self._by_key.get((dst_kind, dst_key))
        if not dst_id:
            return []
        out = []
        for e in self.edges:
            if e.rel == rel and e.dst == dst_id and self.nodes[e.src].kind == "lead":
                out.append(self.nodes[e.src].key)
        return out

    def snapshot(self, lead_id: str) -> dict:
        return {"lead_id": lead_id, "neighbors": self.neighbors("lead", lead_id),
                "nodes": len(self.nodes), "edges": len(self.edges)}


graph = MemoryGraph()
