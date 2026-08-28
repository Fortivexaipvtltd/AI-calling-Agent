from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ..config import settings

# Default propensity by local hour (India calling norms): late morning and
# early evening convert best; midday and late evening worst. Used until we have
# enough per-lead history to override.
_DEFAULT_HOUR_SCORE = {
    9: 0.6, 10: 0.85, 11: 0.9, 12: 0.6, 13: 0.4, 14: 0.55, 15: 0.7,
    16: 0.75, 17: 0.85, 18: 0.9, 19: 0.8,
}


def _in_window(hour: int) -> bool:
    return settings.call_window_start_hour <= hour < settings.call_window_end_hour


def best_hours(history: list[dict] | None = None) -> list[int]:
    """Rank calling-window hours by likelihood of a good connect. `history` is a
    list of {hour, outcome} from past attempts; answered/converted boost an hour,
    no_answer/busy lower it."""
    scores = {h: s for h, s in _DEFAULT_HOUR_SCORE.items() if _in_window(h)}
    for h in range(settings.call_window_start_hour, settings.call_window_end_hour):
        scores.setdefault(h, 0.5)
    for rec in history or []:
        h = rec.get("hour")
        if h is None or not _in_window(h):
            continue
        good = rec.get("outcome") in ("answered", "completed", "converted", "booked")
        scores[h] = min(1.0, max(0.0, scores.get(h, 0.5) + (0.15 if good else -0.1)))
    return sorted(scores, key=lambda h: scores[h], reverse=True)


class BestTimeScheduler:
    """Chooses the next moment to dial: the soonest upcoming instance of a
    high-propensity hour that's inside the calling window and after any backoff."""

    def __init__(self, tz_offset_hours: float = 5.5) -> None:
        # Default IST (+5:30); real deployments pass the lead's tz.
        self.tz_offset = tz_offset_hours

    def _local_now(self, now: datetime) -> datetime:
        return now.astimezone(UTC) + timedelta(hours=self.tz_offset)

    def next_slot(self, *, now: datetime | None = None,
                  not_before: datetime | None = None,
                  history: list[dict] | None = None) -> datetime:
        now = (now or datetime.now(UTC)).astimezone(UTC)
        earliest = max(now, not_before or now)
        ranked = best_hours(history)
        if not ranked:
            return earliest + timedelta(hours=1)
        # Search the next 3 days for the highest-ranked hour at/after `earliest`.
        best_choice = None
        for day in range(0, 3):
            for hour in ranked:
                cand_local = (self._local_now(earliest).replace(
                    hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=day))
                cand_utc = cand_local - timedelta(hours=self.tz_offset)
                cand_utc = cand_utc.replace(tzinfo=UTC)
                if cand_utc >= earliest:
                    rank = ranked.index(hour)
                    if best_choice is None or (day, rank) < best_choice[0]:
                        best_choice = ((day, rank), cand_utc)
            if best_choice and best_choice[0][0] == 0:
                break
        return best_choice[1] if best_choice else earliest + timedelta(hours=1)


scheduler = BestTimeScheduler()
