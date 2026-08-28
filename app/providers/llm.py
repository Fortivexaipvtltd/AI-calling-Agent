from __future__ import annotations

import json
import random
import urllib.request

from ..config import settings

# Conversation rules the wording must always obey.
GUARDRAILS = (
    "You are a warm, natural human admissions counsellor on a live phone call. "
    "Speak in ONE short spoken sentence, like a real person — contractions, light "
    "acknowledgement of what they just said, never robotic. Ask at most one question. "
    "Never invent pricing, guarantees, outcomes or facts: only use the APPROVED FACTS. "
    "Never promise a job; the guarantee is continued support until a better offer, subject to T&C. "
    "Never use any phrase in NEVER_SAY."
)

# Intent → what the line must accomplish (keeps the LLM on-rails).
INTENT_GOAL = {
    "greet": "Warmly greet them by first name and check it's an okay time.",
    "identity": "Politely confirm you're speaking with the right person.",
    "discover": "Ask what's prompting them to look into this now.",
    "clarify_need": "Ask what success would look like for them in the next few months.",
    "INTERESTED": "Acknowledge their interest and ask about their timeline.",
    "HOT": "Match their energy and move toward next steps with a timeline question.",
    "NEEDS_TIME": "Be relaxed, no pressure, ask when a better time would be.",
    "NEEDS_OTHER_DECISION_MAKER": "Offer to share a short summary they can review together.",
    "offer": "Tie the programme to what they shared and offer to explain how it's structured.",
    "objection": "Address their concern honestly using approved facts, then a gentle question.",
    "resolve": "Check whether that resolved their concern or if anything else is on their mind.",
}


class LLMResponder:
    """Generates the actual wording. `local` = deterministic human-ish engine
    (no external calls). `anthropic` = live Claude for natural phrasing, on-rails
    via the planner intent + approved facts, with automatic fallback to local."""

    def __init__(self, provider: str | None = None) -> None:
        self.provider = provider or settings.llm_provider

    def word(self, *, intent: str, lead: dict, product: dict, memory_facts: dict,
             objection: str | None, lead_text: str, history: list[dict]) -> str:
        if self.provider == "byo" and settings.byo_api_key:
            try:
                return self._byo(intent, lead, product, memory_facts,
                                 objection, lead_text, history)
            except Exception:
                pass
        if self.provider == "anthropic" and settings.anthropic_api_key:
            try:
                return self._anthropic(intent, lead, product, memory_facts,
                                       objection, lead_text, history)
            except Exception:
                pass  # never break the call — fall back
        return self._local(intent, lead, product, memory_facts, objection, lead_text)

    # ---- local human-ish engine ------------------------------------------
    def _local(self, intent, lead, product, facts, objection, lead_text) -> str:
        name = (lead.get("name", "") or "there").split(" ")[0]
        ack = self._acknowledge(lead_text)
        outcomes = ", ".join(product.get("outcomes", [])[:2]) or "what you're aiming for"

        bank = {
            "greet": [
                f"Hi {name}, glad I caught you — is now an okay time for a quick chat?",
                f"Hey {name}, hope I'm not catching you at a bad moment — got a quick minute?",
            ],
            "identity": [
                f"Great — just to make sure, am I speaking with {name}?",
                f"Perfect. And you're {name}, right?",
            ],
            "discover": [
                f"{ack}so what's got you looking into this right now?",
                f"{ack}what's prompting you to explore this at the moment?",
            ],
            "clarify_need": [
                f"{ack}what would a good outcome look like for you over the next few months?",
                f"{ack}if this went really well, where would you want to be in a few months?",
            ],
            "INTERESTED": [
                f"{ack}love that — what kind of timeline are you working with?",
                f"That's great to hear, {name} — when are you hoping to get started?",
            ],
            "HOT": [
                f"{ack}I can tell you're keen — what timeline are you thinking?",
                f"Brilliant, {name} — let's line this up. What timeline works for you?",
            ],
            "NEEDS_TIME": [
                "Totally fair, no rush at all — when would be a better time to reach you?",
                f"No pressure, {name} — when should I circle back?",
            ],
            "NEEDS_OTHER_DECISION_MAKER": [
                "Makes sense to loop them in — want me to send a short summary you can go over together?",
                "Of course — shall I email a quick summary you can share with them?",
            ],
            "offer": [
                f"{ack}based on that, this programme's built to help with {outcomes} — want me to walk you through how it's structured?",
                f"From what you've said, this fits well for {outcomes} — shall I explain how it works?",
            ],
            "resolve": [
                "Does that clear it up, or is there anything else on your mind?",
                f"Did that answer it for you, {name}, or anything else you're wondering?",
            ],
        }
        if intent == "objection":
            return self._objection_line(objection, product, name)
        choices = bank.get(intent) or [f"Thanks, {name} — let's line up the next step."]
        return random.choice(choices)

    def _acknowledge(self, lead_text: str) -> str:
        if not lead_text:
            return ""
        t = lead_text.lower()
        if any(w in t for w in ("job", "career", "switch")):
            return "Got it, that's a solid goal — "
        if any(w in t for w in ("expensive", "cost", "budget", "afford")):
            return "I hear you — "
        if any(w in t for w in ("yes", "sure", "okay", "interested")):
            return "Awesome — "
        return "Right — "

    def _objection_line(self, objection, product, name) -> str:
        guarantee = product.get("guarantee", "")
        g = guarantee.split(".")[0].lower() if guarantee else "our support commitment"
        table = {
            "price": f"I hear you on the investment, {name} — many spread it over the plan, and there's {g}. Want me to walk through the options?",
            "time": "Totally fair — it's built for working people, just a few focused hours a week. Would evenings suit you?",
            "trust": "Good thing to check — I can send the official details in writing so you can verify. Shall I email those?",
            "decision": "Makes sense to align with them — want a short summary you can forward?",
            "value": "Fair point — the difference is the structure and mentorship, not scattered free content. Want a quick example?",
        }
        return table.get(objection, "That's a fair concern — happy to talk it through. What's the main worry?")

    # ---- live Claude adapter (drop-in) -----------------------------------
    def _anthropic(self, intent, lead, product, facts, objection, lead_text, history) -> str:
        goal = INTENT_GOAL.get(intent, "Move the sale forward naturally.")
        system = (
            f"{GUARDRAILS}\n\n"
            f"APPROVED FACTS: product={product.get('name','')}; "
            f"outcomes={product.get('outcomes',[])}; guarantee={product.get('guarantee','')}; "
            f"pricing={product.get('pricing_plans',[])}.\n"
            f"NEVER_SAY: {product.get('never_say',[])}.\n"
            f"KNOWN ABOUT LEAD: name={lead.get('name','')}; facts={facts}; "
            f"open_objection={objection or 'none'}.\n"
            f"YOUR GOAL THIS TURN: {goal}\n"
            "Reply with only the spoken sentence, nothing else."
        )
        msgs = [{"role": "assistant" if m["role"] == "agent" else "user",
                 "content": m["text"]} for m in history[-8:] if m.get("text")]
        if lead_text:
            msgs.append({"role": "user", "content": lead_text})
        if not msgs:
            msgs = [{"role": "user", "content": "(call just connected)"}]

        body = json.dumps({
            "model": settings.llm_model, "max_tokens": 120, "system": system, "messages": msgs,
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body,
            headers={"content-type": "application/json",
                     "x-api-key": settings.anthropic_api_key,
                     "anthropic-version": "2023-06-01"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()

    # ---- BYO endpoint (gemini | openai | anthropic protocols) -------------
    def _byo_system(self, intent, lead, product, facts, objection) -> str:
        goal = INTENT_GOAL.get(intent, "Move the sale forward naturally.")
        return (
            f"{GUARDRAILS}\n\n"
            f"APPROVED FACTS: product={product.get('name','')}; "
            f"outcomes={product.get('outcomes',[])}; guarantee={product.get('guarantee','')}; "
            f"pricing={product.get('pricing_plans',[])}.\n"
            f"NEVER_SAY: {product.get('never_say',[])}.\n"
            f"KNOWN ABOUT LEAD: name={lead.get('name','')}; facts={facts}; "
            f"open_objection={objection or 'none'}.\n"
            f"YOUR GOAL THIS TURN: {goal}\n"
            "Reply with only the spoken sentence, nothing else."
        )

    def _detect_protocol(self) -> str:
        p = (settings.byo_protocol or "auto").lower()
        if p != "auto":
            return p
        url = (settings.byo_base_url or "").lower()
        if "generativelanguage" in url or "gemini" in url or "google" in url:
            return "gemini"
        if "anthropic" in url:
            return "anthropic"
        if "openai" in url or "/v1" in url:
            return "openai"
        # Key-shape heuristic: Google AI Studio keys start with AIza.
        if settings.byo_api_key.startswith("AIza"):
            return "gemini"
        return "openai"

    def _byo(self, intent, lead, product, facts, objection, lead_text, history) -> str:
        proto = self._detect_protocol()
        system = self._byo_system(intent, lead, product, facts, objection)
        turns = [(m["role"], m["text"]) for m in history[-8:] if m.get("text")]
        if lead_text:
            turns.append(("lead", lead_text))
        if not turns:
            turns = [("lead", "(call just connected)")]
        if proto == "gemini":
            return self._byo_gemini(system, turns)
        if proto == "anthropic":
            return self._byo_anthropic(system, turns)
        return self._byo_openai(system, turns)

    def _byo_openai(self, system, turns) -> str:
        base = settings.byo_base_url or "https://api.openai.com/v1"
        msgs = [{"role": "system", "content": system}]
        for role, text in turns:
            msgs.append({"role": "assistant" if role == "agent" else "user",
                         "content": text})
        body = json.dumps({"model": settings.byo_model or "gpt-4o-mini",
                           "max_tokens": 120, "messages": msgs}).encode()
        req = urllib.request.Request(
            base.rstrip("/") + "/chat/completions", data=body,
            headers={"content-type": "application/json",
                     "authorization": f"Bearer {settings.byo_api_key}"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"].strip()

    def _byo_anthropic(self, system, turns) -> str:
        base = settings.byo_base_url or "https://api.anthropic.com"
        msgs = [{"role": "assistant" if r == "agent" else "user", "content": t}
                for r, t in turns]
        body = json.dumps({"model": settings.byo_model or "claude-sonnet-4-6",
                           "max_tokens": 120, "system": system, "messages": msgs}).encode()
        req = urllib.request.Request(
            base.rstrip("/") + "/v1/messages", data=body,
            headers={"content-type": "application/json",
                     "x-api-key": settings.byo_api_key,
                     "anthropic-version": "2023-06-01"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        return "".join(b.get("text", "") for b in data.get("content", [])
                       if b.get("type") == "text").strip()

    def _byo_gemini(self, system, turns) -> str:
        model = settings.byo_model or "gemini-1.5-flash"
        base = settings.byo_base_url or "https://generativelanguage.googleapis.com/v1beta"
        contents = []
        for role, text in turns:
            contents.append({"role": "model" if role == "agent" else "user",
                             "parts": [{"text": text}]})
        body = json.dumps({
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {"maxOutputTokens": 120, "temperature": 0.7},
        }).encode()
        url = f"{base.rstrip('/')}/models/{model}:generateContent?key={settings.byo_api_key}"
        req = urllib.request.Request(url, data=body,
                                     headers={"content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        cand = (data.get("candidates") or [{}])[0]
        parts = (cand.get("content") or {}).get("parts") or [{}]
        return "".join(p.get("text", "") for p in parts).strip()
