from __future__ import annotations

from ..agent_runtime import sales


def extract_facts(transcript: list[dict]) -> dict:
    """Convert a conversation into durable structured facts + insights."""
    lead_lines = [t["text"] for t in transcript if t["role"] == "lead"]
    joined = " ".join(lead_lines).lower()

    facts: dict[str, str] = {}
    if any(w in joined for w in ("job", "career", "become", "switch")):
        facts["goal"] = next((l for l in lead_lines if any(w in l.lower()
                             for w in ("job", "career", "become", "switch"))), "")
    for line in lead_lines:
        for token in line.replace(",", " ").split():
            digits = "".join(ch for ch in token if ch.isdigit())
            if digits and len(digits) >= 4:
                facts["budget"] = token
    if any(w in joined for w in ("month", "week", "asap", "immediately")):
        facts["timeline"] = next((l for l in lead_lines if any(w in l.lower()
                                 for w in ("month", "week", "asap", "immediately"))), "")

    objections: list[str] = []
    for line in lead_lines:
        obj = sales.detect_objection(line)
        if obj and obj not in objections:
            objections.append(obj)

    sentiment = "neutral"
    if any(w in joined for w in ("interested", "great", "yes", "ready")):
        sentiment = "positive"
    if any(w in joined for w in ("not interested", "no", "busy", "stop")):
        sentiment = "negative"

    summary = _summarize(lead_lines)
    return {"facts": facts, "objections": objections, "sentiment": sentiment, "summary": summary}


def _summarize(lead_lines: list[str]) -> str:
    if not lead_lines:
        return "No lead speech captured."
    first = lead_lines[0][:80]
    last = lead_lines[-1][:80]
    return f"Lead opened with '{first}' and closed with '{last}'."
