from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..ai.rag import store as rag_store
from ..providers.stt import STTProvider
from ..tools.registry import ToolRegistry


@dataclass
class Event:
    modality: str            # text | audio | image | dtmf | tool_result
    payload: Any


@dataclass
class MultimodalRuntime:
    """One runtime that accepts any input modality and normalizes it to text the
    agent core can reason over: audio -> STT, image -> caption stub, DTMF -> digits,
    tool_result -> observation. This is the substrate for voice, chat and app
    surfaces sharing a single agent."""

    tools: ToolRegistry = field(default_factory=ToolRegistry)
    stt: STTProvider = field(default_factory=STTProvider)
    history: list[dict] = field(default_factory=list)

    def ingest(self, event: Event) -> dict:
        norm = self._normalize(event)
        self.history.append(norm)
        return norm

    def _normalize(self, event: Event) -> dict:
        if event.modality == "text":
            return {"modality": "text", "text": str(event.payload)}
        if event.modality == "audio":
            words = event.payload if isinstance(event.payload, list) else []
            out = self.stt.transcribe(words=words)
            return {"modality": "audio", "text": out.get("transcript", "")}
        if event.modality == "image":
            meta = event.payload if isinstance(event.payload, dict) else {"ref": event.payload}
            return {"modality": "image", "text": f"[image: {meta.get('caption','uploaded')}]",
                    "meta": meta}
        if event.modality == "dtmf":
            return {"modality": "dtmf", "text": f"[keypad: {event.payload}]",
                    "digits": str(event.payload)}
        if event.modality == "tool_result":
            return {"modality": "tool_result", "text": f"[observation: {event.payload}]",
                    "result": event.payload}
        return {"modality": event.modality, "text": str(event.payload)}

    def as_text(self) -> str:
        return " ".join(h["text"] for h in self.history if h.get("text"))

    def retrieve(self, query: str) -> list[dict]:
        return rag_store.search(query)

    def act(self, tool: str, args: dict) -> dict:
        res = self.tools.call(tool, args)
        self.history.append({"modality": "tool_result", "text": f"[{tool} -> {res.get('ok')}]",
                             "result": res})
        return res
