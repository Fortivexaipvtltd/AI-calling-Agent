from __future__ import annotations

from .memory import Memory

POSITIVE = {"yes", "sure", "interested", "okay", "ok", "great", "sounds good", "let's", "definitely"}
NEGATIVE = {"no", "not interested", "busy", "later", "stop", "don't"}
OBJECTIONS = {
    "price": {"expensive", "costly", "afford", "price", "budget", "too much", "fees"},
    "time": {"no time", "busy", "later", "schedule"},
    "trust": {"scam", "trust", "genuine", "real", "guarantee", "fake"},
    "decision": {"my parents", "wife", "husband", "manager", "think about", "discuss"},
    "value": {"why", "worth", "already know", "free on youtube"},
}


def disengagement(text: str) -> str | None:
    """Detect disengagement at ANY conversation state."""
    t = text.lower()
    if any(w in t for w in ("not interested", "no thanks", "don't call", "leave me")):
        return "NOT_INTERESTED"
    if any(w in t for w in ("parents", "my wife", "my husband", "my manager", "discuss with", "talk to my")):
        return "NEEDS_OTHER_DECISION_MAKER"
    if any(w in t for w in ("next month", "not now", "call me later", "some other time")):
        return "NEEDS_TIME"
    return None


def classify_qualification(text: str, memory: Memory) -> str:
    t = text.lower()
    if any(w in t for w in ("not interested", "no thanks", "don't call")):
        return "NOT_INTERESTED"
    if any(w in t for w in ("parents", "wife", "husband", "manager", "discuss with")):
        return "NEEDS_OTHER_DECISION_MAKER"
    if any(w in t for w in ("later", "next month", "not now", "think about")):
        return "NEEDS_TIME"
    if "budget" in memory.facts and _is_low_budget(memory.facts["budget"].value):
        return "NOT_A_FIT"
    if any(w in t for w in ("very interested", "ready", "sign up", "enroll", "pay")):
        return "HOT"
    if any(w in t for w in POSITIVE):
        return "INTERESTED"
    return "INTERESTED"


def _is_low_budget(value: str) -> bool:
    digits = "".join(ch for ch in value if ch.isdigit())
    return bool(digits) and int(digits) < 5000


def detect_objection(text: str) -> str | None:
    t = text.lower()
    for name, triggers in OBJECTIONS.items():
        if any(trig in t for trig in triggers):
            return name
    return None


def objection_response(name: str, product: dict) -> str:
    guarantee = product.get("guarantee", "")
    table = {
        "price": (
            "I hear you on the investment. Many learners spread it across the plan, "
            f"and there's the {guarantee.split('.')[0].lower() or 'support commitment'}. "
            "Want me to walk through the plan?"
        ),
        "time": "Totally fair. It's built for working people — a few focused hours a week. "
        "Would evenings suit you better?",
        "trust": "Good question to ask. I can send the official details and outcomes in writing "
        "so you can verify. Shall I email those?",
        "decision": "Makes sense to align with them. Would it help if I shared a short summary "
        "you can forward, and we set a follow-up together?",
        "value": "Fair point. The difference is structure, mentorship and accountability rather "
        "than scattered free content. Want a quick example of that?",
    }
    return table.get(name, "That's a fair concern — let me address it clearly.")


def score_lead(memory: Memory, qualification: str) -> tuple[int, float]:
    score = 40
    for k in ("goal", "budget", "timeline"):
        if k in memory.facts:
            score += 12
    bump = {"HOT": 25, "INTERESTED": 12, "NEEDS_TIME": -5, "NOT_INTERESTED": -30, "NOT_A_FIT": -20}
    score += bump.get(qualification, 0)
    score = max(0, min(100, score))
    return score, round(score / 100, 2)


DISCOVERY_QUESTIONS = [
    "What's prompting you to look at this right now?",
    "What would success look like for you in the next few months?",
]

QUALIFICATION_QUESTIONS = [
    "What kind of timeline are you working with?",
    "Have you set aside a budget for something like this?",
]
