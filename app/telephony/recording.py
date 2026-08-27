from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from ..config import settings


def _id(p: str) -> str:
    return f"{p}_{uuid.uuid4().hex[:10]}"


@dataclass
class Recording:
    call_id: str
    id: str = field(default_factory=lambda: _id("rec"))
    channels: int = 2            # dual channel: lead + agent
    status: str = "recording"
    consent: bool = True
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    ended_at: str = ""
    uri: str = ""


class RecordingService:
    """Records calls when enabled and consented. Local store keeps metadata and
    a URI; a real object store (S3/GCS) is a drop-in behind `RECORDING_STORE`."""

    def __init__(self) -> None:
        self.recordings: dict[str, Recording] = {}

    def start(self, call_id: str, consent: bool = True) -> dict:
        if not settings.recording_enabled:
            return {"ok": False, "error": "recording_disabled"}
        if not consent:
            return {"ok": False, "error": "no_consent"}
        rec = Recording(call_id=call_id, consent=consent)
        self.recordings[rec.id] = rec
        return {"ok": True, "recording_id": rec.id, "status": rec.status}

    def stop(self, recording_id: str) -> dict:
        rec = self.recordings.get(recording_id)
        if not rec:
            return {"ok": False, "error": "unknown_recording"}
        rec.status = "stored"
        rec.ended_at = datetime.utcnow().isoformat()
        rec.uri = f"{settings.recording_store.rstrip('/')}/{rec.id}.wav"
        return {"ok": True, "recording_id": rec.id, "uri": rec.uri, "status": rec.status}

    def get(self, recording_id: str) -> dict:
        rec = self.recordings.get(recording_id)
        return rec.__dict__ if rec else {}


recordings = RecordingService()
