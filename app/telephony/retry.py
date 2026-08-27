from __future__ import annotations

from datetime import datetime, timedelta

from ..config import settings

# Outcomes that are worth retrying vs. terminal.
RETRYABLE = {"no_answer", "busy", "failed", "voicemail", "machine"}
TERMINAL = {"completed", "answered", "opted_out", "converted"}


class RetryPolicy:
    """Decides whether and when to re-dial. Exponential-ish backoff capped by
    `max_retries_per_lead`; respects the calling window elsewhere in compliance."""

    def __init__(self, max_retries: int | None = None,
                 backoff_minutes: int | None = None) -> None:
        self.max_retries = max_retries or settings.max_retries_per_lead
        self.backoff = backoff_minutes or settings.retry_backoff_minutes

    def should_retry(self, outcome: str, attempts: int) -> bool:
        if outcome in TERMINAL:
            return False
        return outcome in RETRYABLE and attempts < self.max_retries

    def next_attempt_at(self, attempts: int, now: datetime | None = None) -> datetime:
        now = now or datetime.utcnow()
        # 1x, 2x, 4x backoff.
        factor = 2 ** max(0, attempts - 1)
        return now + timedelta(minutes=self.backoff * factor)

    def plan(self, outcome: str, attempts: int, now: datetime | None = None) -> dict:
        if not self.should_retry(outcome, attempts):
            return {"retry": False, "reason": outcome, "attempts": attempts}
        at = self.next_attempt_at(attempts + 1, now)
        return {"retry": True, "attempt": attempts + 1, "at": at.isoformat(),
                "reason": outcome}


policy = RetryPolicy()
