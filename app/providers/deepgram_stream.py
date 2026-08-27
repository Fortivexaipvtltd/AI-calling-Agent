from __future__ import annotations

import json
from collections.abc import Callable

from ..config import settings

DG_WS = "wss://api.deepgram.com/v1/listen"


class DeepgramStream:
    """Real-time streaming STT over Deepgram's WebSocket API.

    Requires the `websockets` package (optional dependency). Audio chunks are
    sent as they arrive; interim/final transcripts are delivered to `on_transcript`.
    Use this when you own the media socket (e.g. bridging Twilio Media Streams)
    and want partials rather than per-utterance prerecorded calls.

        stream = DeepgramStream(on_transcript=cb)
        await stream.connect(encoding="mulaw", sample_rate=8000)
        await stream.send(audio_bytes)
        await stream.finish()
    """

    def __init__(self, on_transcript: Callable[[dict], None] | None = None) -> None:
        self.on_transcript = on_transcript or (lambda _: None)
        self._ws = None

    def _url(self, encoding: str, sample_rate: int) -> str:
        q = (f"?model=nova-2&smart_format=true&interim_results=true"
             f"&encoding={encoding}&sample_rate={sample_rate}")
        return DG_WS + q

    async def connect(self, encoding: str = "mulaw", sample_rate: int = 8000) -> None:
        import websockets  # optional; install to enable streaming

        self._ws = await websockets.connect(
            self._url(encoding, sample_rate),
            additional_headers={"Authorization": f"Token {settings.stt_api_key}"},
        )

    async def send(self, chunk: bytes) -> None:
        if self._ws:
            await self._ws.send(chunk)

    async def recv_loop(self) -> None:
        if not self._ws:
            return
        async for message in self._ws:
            data = json.loads(message)
            alt = (data.get("channel", {}).get("alternatives") or [{}])[0]
            text = alt.get("transcript", "")
            if text:
                self.on_transcript({"text": text, "is_final": data.get("is_final", False),
                                    "confidence": alt.get("confidence", 0.0)})

    async def finish(self) -> None:
        if self._ws:
            await self._ws.send(json.dumps({"type": "CloseStream"}))
            await self._ws.close()
            self._ws = None
