from __future__ import annotations

import json
import re

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class SchemaError(Exception):
    pass


def _coerce(value, typ: str):
    try:
        if typ == "integer":
            return int(value)
        if typ == "number":
            return float(value)
        if typ == "boolean":
            return bool(value) if isinstance(value, bool) else str(value).lower() in ("true", "1", "yes")
        if typ == "string":
            return str(value)
        if typ == "array":
            return list(value) if isinstance(value, (list, tuple)) else [value]
        if typ == "object":
            return dict(value)
    except Exception as exc:
        raise SchemaError(f"cannot coerce to {typ}: {exc}") from exc
    return value


def validate(obj: dict, schema: dict) -> dict:
    """Minimal JSON-Schema subset: type, properties, required. Coerces scalars."""
    if schema.get("type", "object") != "object":
        raise SchemaError("top-level schema must be object")
    props = schema.get("properties", {})
    out: dict = {}
    for key, spec in props.items():
        if key in obj:
            out[key] = _coerce(obj[key], spec.get("type", "string"))
        elif "default" in spec:
            out[key] = spec["default"]
    for req in schema.get("required", []):
        if req not in out:
            raise SchemaError(f"missing required field: {req}")
    return out


def parse(text: str, schema: dict) -> dict:
    """Extract JSON from possibly-noisy model text and validate it."""
    cleaned = text.strip().replace("```json", "").replace("```", "").strip()
    match = _JSON_BLOCK.search(cleaned)
    raw = match.group(0) if match else cleaned
    try:
        obj = json.loads(raw)
    except Exception as exc:
        raise SchemaError(f"not valid JSON: {exc}") from exc
    return validate(obj, schema)


def system_prompt_for(schema: dict) -> str:
    """Instruction appended to an LLM system prompt to force structured output."""
    keys = ", ".join(schema.get("properties", {}))
    return ("Respond with ONLY a single JSON object, no prose, no markdown fences. "
            f"Keys: {keys}. Required: {schema.get('required', [])}.")


# Ready-made schema used by the post-call worker.
LEAD_INSIGHT_SCHEMA = {
    "type": "object",
    "properties": {
        "sentiment": {"type": "string", "default": "neutral"},
        "score": {"type": "integer", "default": 0},
        "objections": {"type": "array", "default": []},
        "next_action": {"type": "string", "default": "followup_call_48h"},
    },
    "required": ["sentiment", "next_action"],
}
