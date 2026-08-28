from __future__ import annotations

from datetime import UTC, datetime

from ..config import settings
from . import dnc
from .best_time import scheduler as best_time
from .retry import policy as retry_policy


class CampaignDialer:
    """Bulk outbound engine. Given a campaign's queued tasks it:
      - respects max concurrency (in-flight calls) and calls-per-minute rate,
      - skips numbers on the DNC list and leads outside the calling window,
      - places the call via the telephony provider (real Twilio when configured),
      - on a bad outcome, reschedules via best-time + retry backoff,
    all on durable CampaignTask rows so a run survives restarts / many workers.
    """

    def __init__(self, max_concurrent: int | None = None,
                 calls_per_min: int | None = None) -> None:
        self.max_concurrent = max_concurrent or settings.dialer_max_concurrent
        self.calls_per_min = calls_per_min or settings.dialer_calls_per_min

    def _window_ok(self, now: datetime) -> bool:
        local_hour = (now.astimezone(UTC).hour + 5) % 24  # ~IST coarse
        return settings.call_window_start_hour <= local_hour < settings.call_window_end_hour

    def load_campaign(self, db, campaign_id: str, lead_ids: list[str]) -> int:
        """Create one queued task per lead (idempotent per lead+campaign)."""
        from sqlalchemy import select

        from ..models import CampaignTask
        existing = set(db.scalars(
            select(CampaignTask.lead_id).where(CampaignTask.campaign_id == campaign_id)).all())
        made = 0
        for lid in lead_ids:
            if lid in existing:
                continue
            db.add(CampaignTask(campaign_id=campaign_id, org_id=settings.default_org_id,
                                lead_id=lid, status="queued",
                                next_at=datetime.now(UTC)))
            made += 1
        db.flush()
        return made

    def tick(self, db, campaign_id: str, *, now: datetime | None = None,
             dial_fn=None, limit: int | None = None) -> dict:
        """Process one scheduling tick: place up to (concurrency, rate, limit)
        due calls. `dial_fn(lead)` lets tests inject a fake dialer; default uses
        the real Twilio voice client."""
        from sqlalchemy import select

        from ..models import CampaignTask, Lead
        now = now or datetime.now(UTC)
        result = {"placed": 0, "skipped_dnc": 0, "skipped_window": 0,
                  "rescheduled": 0, "done": 0, "remaining": 0}

        if not self._window_ok(now):
            pending = db.scalars(select(CampaignTask).where(
                CampaignTask.campaign_id == campaign_id,
                CampaignTask.status == "queued")).all()
            result["skipped_window"] = len(pending)
            result["remaining"] = len(pending)
            return result

        in_flight = len(db.scalars(select(CampaignTask).where(
            CampaignTask.campaign_id == campaign_id,
            CampaignTask.status == "dialing")).all())
        budget = min(self.max_concurrent - in_flight, self.calls_per_min,
                     limit if limit is not None else self.calls_per_min)

        due = db.scalars(select(CampaignTask).where(
            CampaignTask.campaign_id == campaign_id,
            CampaignTask.status == "queued",
            CampaignTask.next_at <= now).order_by(CampaignTask.next_at)).all()

        for task in due:
            if result["placed"] >= max(0, budget):
                break
            lead = db.get(Lead, task.lead_id)
            if not lead:
                task.status = "skipped"
                task.outcome = "no_lead"
                continue
            if dnc.is_blocked(db, lead.phone) or getattr(lead, "suppressed", False):
                task.status = "skipped"
                task.outcome = "dnc"
                result["skipped_dnc"] += 1
                continue
            outcome = self._place(db, lead, task, dial_fn)
            task.attempts += 1
            if outcome in ("answered", "completed", "converted", "booked"):
                task.status = "done"
                task.outcome = outcome
                result["placed"] += 1
                result["done"] += 1
            else:
                plan = retry_policy.plan(outcome, task.attempts, now)
                if plan.get("retry"):
                    hist = [{"hour": now.hour, "outcome": outcome}]
                    task.next_at = best_time.next_slot(now=now, history=hist)
                    task.status = "queued"
                    task.outcome = outcome
                    result["rescheduled"] += 1
                else:
                    task.status = "failed"
                    task.outcome = outcome
                result["placed"] += 1
        db.flush()
        result["remaining"] = len(db.scalars(select(CampaignTask).where(
            CampaignTask.campaign_id == campaign_id,
            CampaignTask.status == "queued")).all())
        db.commit()
        return result

    def _place(self, db, lead, task, dial_fn) -> str:
        if dial_fn is not None:
            res = dial_fn(lead)
            task.provider_call_id = res.get("provider_call_id", "")
            return res.get("outcome", res.get("status", "no_answer"))
        from .provider import dial as _dial
        res = _dial(lead.phone, task.id)
        task.provider_call_id = res.get("provider_call_id", "")
        status = res.get("status", "")
        return "answered" if status in ("completed", "in-progress", "queued") else "no_answer"

    def stats(self, db, campaign_id: str) -> dict:
        from sqlalchemy import select

        from ..models import CampaignTask
        tasks = db.scalars(select(CampaignTask).where(
            CampaignTask.campaign_id == campaign_id)).all()
        by = {}
        for t in tasks:
            by[t.status] = by.get(t.status, 0) + 1
        done = [t for t in tasks if t.status == "done"]
        return {"total": len(tasks), "by_status": by,
                "connect_rate": round(len(done) / len(tasks), 3) if tasks else 0.0}


dialer = CampaignDialer()
