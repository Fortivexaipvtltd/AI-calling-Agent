from __future__ import annotations

from datetime import datetime

from .config import settings


class ComplianceError(Exception):
    pass


def check_call_permission(lead, at: datetime | None = None) -> tuple[bool, str]:
    at = at or datetime.now()
    if getattr(lead, "suppressed", False):
        return False, "lead_suppressed"
    if lead.attempts >= settings.max_attempts_per_lead:
        return False, "max_attempts_reached"
    if not (settings.call_window_start_hour <= at.hour < settings.call_window_end_hour):
        return False, "outside_calling_window"
    return True, "ok"


def enforce_call_permission(lead, at: datetime | None = None) -> None:
    ok, reason = check_call_permission(lead, at)
    if not ok:
        raise ComplianceError(reason)


REQUIRED_DISCLOSURE = (
    "Hi, this is an assisted call from the admissions desk. "
    "Is now an okay time to talk for a minute?"
)


def contains_opt_out(text: str) -> bool:
    t = text.lower()
    return any(
        phrase in t
        for phrase in ("stop calling", "do not call", "don't call", "remove me", "unsubscribe")
    )
