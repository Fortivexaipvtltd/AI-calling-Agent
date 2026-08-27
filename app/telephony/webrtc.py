from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from ..config import settings


def _id(p: str) -> str:
    return f"{p}_{uuid.uuid4().hex[:10]}"


@dataclass
class RTCSession:
    id: str = field(default_factory=lambda: _id("rtc"))
    state: str = "new"  # new | connecting | connected | closed
    ice_servers: list[str] = field(default_factory=list)
    remote_sdp: str = ""
    local_sdp: str = ""


class WebRTCGateway:
    """Browser calling over WebRTC. `local` returns a synthetic SDP answer so
    the signalling flow is exercised end to end; livekit/daily drop in for real
    media. This is what powers "call from the browser" with no phone number."""

    def __init__(self, provider: str | None = None) -> None:
        self.provider = provider or settings.webrtc_provider
        self.sessions: dict[str, RTCSession] = {}

    def ice_servers(self) -> list[str]:
        return [s.strip() for s in settings.webrtc_ice_servers.split(",") if s.strip()]

    def offer(self, remote_sdp: str) -> dict:
        """Accept a browser SDP offer, return an SDP answer + session id."""
        sess = RTCSession(ice_servers=self.ice_servers(), remote_sdp=remote_sdp,
                          state="connecting")
        sess.local_sdp = self._answer_sdp(sess.id)
        self.sessions[sess.id] = sess
        return {"provider": self.provider, "session_id": sess.id,
                "sdp_answer": sess.local_sdp, "ice_servers": sess.ice_servers}

    def connected(self, session_id: str) -> dict:
        sess = self.sessions.get(session_id)
        if not sess:
            return {"ok": False, "error": "unknown_session"}
        sess.state = "connected"
        return {"ok": True, "session_id": session_id, "state": sess.state}

    def close(self, session_id: str) -> dict:
        sess = self.sessions.get(session_id)
        if sess:
            sess.state = "closed"
        return {"ok": bool(sess), "session_id": session_id, "state": "closed"}

    def _answer_sdp(self, sid: str) -> str:
        codec = settings.default_codec
        return (f"v=0\r\no=- {sid} 2 IN IP4 127.0.0.1\r\ns=highh\r\n"
                f"m=audio 9 UDP/TLS/RTP/SAVPF 111\r\na=rtpmap:111 {codec}/48000/2\r\n"
                "a=sendrecv\r\n")


gateway = WebRTCGateway()
