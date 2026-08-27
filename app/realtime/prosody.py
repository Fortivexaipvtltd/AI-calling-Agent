from __future__ import annotations

import re
from dataclasses import dataclass
from xml.sax.saxutils import escape

from .voice_profile import profile as _profile

_CURRENCY = re.compile(r"(?:₹|Rs\.?|INR)\s?([\d,]+)", re.IGNORECASE)
_PLAIN_NUM = re.compile(r"\b(\d{4,})\b")
_ABBREV = {
    "AI": "A I", "ML": "M L", "EMI": "E M I", "GenAI": "Gen A I",
    "IIT": "I I T", "&": "and",
}


def _speak_indian_number(n: int) -> str:
    """Render a rupee amount the way an Indian speaker says it (lakh/crore)."""
    if n >= 10_000_000:
        return f"{n / 10_000_000:.2f}".rstrip("0").rstrip(".") + " crore"
    if n >= 100_000:
        return f"{n / 100_000:.2f}".rstrip("0").rstrip(".") + " lakh"
    if n >= 1000:
        return f"{n / 1000:.1f}".rstrip("0").rstrip(".") + " thousand"
    return str(n)


def normalize_for_speech(text: str) -> str:
    """Make raw text sound natural when spoken: currency in lakh/crore, big
    numbers spaced, and abbreviations expanded so TTS doesn't spell oddly."""
    def _cur(m: re.Match) -> str:
        digits = int(m.group(1).replace(",", ""))
        return "rupees " + _speak_indian_number(digits)
    out = _CURRENCY.sub(_cur, text)
    out = _PLAIN_NUM.sub(lambda m: _speak_indian_number(int(m.group(1))), out)
    for k, v in _ABBREV.items():
        out = re.sub(rf"\b{re.escape(k)}\b", v, out)
    return out


@dataclass
class ProsodyOptions:
    intent_style: str = "default"
    add_opener: bool = True
    emphasis: bool = True


def split_clauses(text: str) -> list[str]:
    """Segment into clauses for streaming: sentence enders and strong commas
    become clause boundaries so we can synthesize/emit speech incrementally."""
    parts = re.split(r"(?<=[.!?])\s+|(?<=,)\s+|\s+—\s+", text.strip())
    return [p for p in (s.strip() for s in parts) if p]


def _emphasize(clause: str) -> str:
    words = []
    for w in clause.split():
        bare = re.sub(r"[^\w]", "", w).lower()
        if bare in _profile.emphasis_words:
            lead = w[: len(w) - len(w.lstrip())]
            words.append(f"{lead}<emphasis level=\"moderate\">{escape(w.strip())}</emphasis>")
        else:
            words.append(escape(w))
    return " ".join(words)


class ProsodyEngine:
    """Turns a plain agent line into human-sounding SSML: an optional opener,
    clause-level pacing, mid-sentence micro-pauses, light emphasis on value
    words, and an intent-appropriate rate/pitch. Also exposes the plain
    normalized text for engines that don't accept SSML."""

    def style_for(self, intent: str) -> str:
        if intent in ("handle_objection", "objection", "acknowledge"):
            return "objection"
        if intent in ("empathize", "reassure", "repair"):
            return "empathy"
        if intent in ("confirm", "close", "book", "payment"):
            return "confirm"
        if intent in ("discover", "clarify_need", "qualify"):
            return "discover"
        return "default"

    def to_ssml(self, text: str, *, intent: str = "", opts: ProsodyOptions | None = None) -> str:
        style_key = opts.intent_style if opts and opts.intent_style != "default" \
            else self.style_for(intent)
        style = _profile.style(style_key)
        opts = opts or ProsodyOptions(intent_style=style_key)
        spoken = normalize_for_speech(text)
        clauses = split_clauses(spoken)

        body_parts: list[str] = []
        if opts.add_opener and style.opener:
            body_parts.append(
                f"{escape(style.opener)}<break time=\"{_profile.opener_pause_ms}ms\"/>")
        for i, clause in enumerate(clauses):
            rendered = _emphasize(clause) if opts.emphasis else escape(clause)
            body_parts.append(rendered)
            ends_sentence = clause.endswith((".", "!", "?"))
            pause = style.sentence_pause_ms if ends_sentence else _profile.comma_pause_ms
            if i < len(clauses) - 1:
                body_parts.append(f"<break time=\"{pause}ms\"/>")
        inner = " ".join(body_parts)
        return (f"<speak><prosody rate=\"{style.rate}\" pitch=\"{style.pitch}\">"
                f"{inner}</prosody></speak>")

    def plain(self, text: str) -> str:
        return normalize_for_speech(text)


engine = ProsodyEngine()
