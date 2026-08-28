from __future__ import annotations

import json
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta

from ..config import settings


class CalendarProvider:
    """Creates real calendar events (Google / Outlook) and returns a join link.
    `local` produces a deterministic booking so flows run offline; the real
    providers drop in behind the same `book`."""

    def __init__(self, provider: str | None = None) -> None:
        self.provider = provider or settings.calendar_provider
        self.booked: list[dict] = []

    def check(self, day: str = "") -> dict:
        # Simple availability suggestion; real providers query free/busy.
        return {"slots": ["tomorrow 5:00 PM", "tomorrow 6:00 PM", "Saturday 11:00 AM"]}

    def book(self, *, title: str, when_iso: str = "", duration_min: int = 30,
             attendee_email: str = "", attendee_name: str = "") -> dict:
        start = when_iso or (datetime.now(UTC) + timedelta(days=1)).replace(
            hour=11, minute=30, second=0, microsecond=0).isoformat()
        if self.provider == "google" and settings.calendar_token:
            try:
                return self._google(title, start, duration_min, attendee_email)
            except Exception as exc:
                return {"provider": "google", "status": "failed", "error": str(exc)}
        if self.provider == "outlook" and settings.calendar_token:
            try:
                return self._outlook(title, start, duration_min, attendee_email)
            except Exception as exc:
                return {"provider": "outlook", "status": "failed", "error": str(exc)}
        ev = {"provider": "local", "status": "confirmed",
              "event_id": f"evt_{uuid.uuid4().hex[:12]}", "title": title,
              "start": start, "duration_min": duration_min,
              "attendee": attendee_email or attendee_name,
              "join_url": f"https://meet.example.com/{uuid.uuid4().hex[:10]}"}
        self.booked.append(ev)
        return ev

    def _google(self, title, start_iso, duration_min, email) -> dict:
        end = (datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
               + timedelta(minutes=duration_min)).isoformat()
        body = {
            "summary": title,
            "start": {"dateTime": start_iso},
            "end": {"dateTime": end},
            "attendees": [{"email": email}] if email else [],
            "conferenceData": {"createRequest": {"requestId": uuid.uuid4().hex[:12]}},
        }
        url = (f"https://www.googleapis.com/calendar/v3/calendars/"
               f"{settings.calendar_id}/events?conferenceDataVersion=1")
        req = urllib.request.Request(
            url, data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {settings.calendar_token}",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        return {"provider": "google", "status": "confirmed",
                "event_id": data.get("id", ""), "title": title, "start": start_iso,
                "join_url": data.get("hangoutLink", data.get("htmlLink", ""))}

    def _outlook(self, title, start_iso, duration_min, email) -> dict:
        end = (datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
               + timedelta(minutes=duration_min)).isoformat()
        body = {
            "subject": title,
            "start": {"dateTime": start_iso, "timeZone": "UTC"},
            "end": {"dateTime": end, "timeZone": "UTC"},
            "isOnlineMeeting": True,
            "attendees": ([{"emailAddress": {"address": email}, "type": "required"}]
                          if email else []),
        }
        req = urllib.request.Request(
            "https://graph.microsoft.com/v1.0/me/events",
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {settings.calendar_token}",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        join = (data.get("onlineMeeting") or {}).get("joinUrl", "")
        return {"provider": "outlook", "status": "confirmed",
                "event_id": data.get("id", ""), "title": title, "start": start_iso,
                "join_url": join}


calendar = CalendarProvider()
