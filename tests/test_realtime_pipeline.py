from __future__ import annotations

import asyncio
import audioop
import base64

from app.realtime.pipeline import TWILIO_FRAME_BYTES, RealtimeCallPipeline


class FakeSTT:
    """Returns a fixed transcript whenever the local endpointer flushes audio."""

    def __init__(self, text="i want an ai job"):
        self.text = text

    def transcribe(self, *, audio=None, content_type=""):
        return {"provider": "fake", "transcript": self.text}


def _ulaw_frame(amplitude: int) -> str:
    pcm = bytes([amplitude & 0xFF, (amplitude >> 8) & 0xFF]) * 160  # 20ms @ 8k
    return base64.b64encode(audioop.lin2ulaw(pcm, 2)).decode()


LOUD = _ulaw_frame(0x2000)
QUIET = _ulaw_frame(0x0000)


def _pipeline(on_turn, **kw):
    sent = []

    async def send(frame):
        sent.append(frame)

    p = RealtimeCallPipeline(call_id="call_rt", send=send, on_turn=on_turn, **kw)
    p._bridge.stt = FakeSTT()          # local endpointer returns a transcript
    p._bridge.endpoint_silence_frames = 2
    return p, sent


def test_full_duplex_loop_produces_outbound_media():
    calls = {}

    def on_turn(text):
        calls["text"] = text
        return "Great, let's get you enrolled today.", "confirm", False

    async def run():
        p, sent = _pipeline(on_turn)
        await p.handle_event({"event": "start", "start": {"streamSid": "MZ1"}})
        await p.handle_event({"event": "media", "media": {"payload": LOUD}})
        await p.handle_event({"event": "media", "media": {"payload": QUIET}})
        await p.handle_event({"event": "media", "media": {"payload": QUIET}})
        await p.drain()
        return p, sent

    p, sent = asyncio.get_event_loop().run_until_complete(run())
    # transcript reached the LLM
    assert calls["text"] == "i want an ai job"
    # agent audio streamed back to Twilio as media frames with the right stream sid
    media = [f for f in sent if f.get("event") == "media"]
    assert media and all(f["streamSid"] == "MZ1" for f in media)
    # each frame is valid base64 mu-law of one 20ms frame
    payload = base64.b64decode(media[0]["media"]["payload"])
    assert 0 < len(payload) <= TWILIO_FRAME_BYTES
    assert p.metrics.frames_sent == len(media)


def test_barge_in_sends_clear_and_stops_speaking():
    def on_turn(text):
        # long reply -> many outbound frames, giving us time to interrupt
        return ("Here is a very long explanation " * 12).strip(), "", False

    async def run():
        p, sent = _pipeline(on_turn)
        await p.handle_event({"event": "start", "start": {"streamSid": "MZ2"}})
        # trigger a transcript -> starts speaking task
        await p.handle_event({"event": "media", "media": {"payload": LOUD}})
        await p.handle_event({"event": "media", "media": {"payload": QUIET}})
        await p.handle_event({"event": "media", "media": {"payload": QUIET}})
        # let a few outbound frames go out
        await asyncio.sleep(0)
        frames_before = p.metrics.frames_sent
        # caller talks over the agent -> barge-in
        await p.handle_event({"event": "media", "media": {"payload": LOUD}})
        await p.drain()
        return p, sent, frames_before

    p, sent, before = asyncio.get_event_loop().run_until_complete(run())
    assert p.metrics.barge_ins >= 1
    assert any(f.get("event") == "clear" and f["streamSid"] == "MZ2" for f in sent)
    assert p.speaking is False


def test_stop_event_flushes_final_transcript():
    seen = {}

    def on_turn(text):
        seen["text"] = text
        return "Thanks, talk soon.", "confirm", True

    async def run():
        p, sent = _pipeline(on_turn)
        await p.handle_event({"event": "start", "start": {"streamSid": "MZ3"}})
        await p.handle_event({"event": "media", "media": {"payload": LOUD}})
        # no silence endpoint; the stop event should flush the buffer
        await p.handle_event({"event": "stop"})
        await p.drain()
        return p, sent

    p, sent = asyncio.get_event_loop().run_until_complete(run())
    assert seen.get("text") == "i want an ai job"
    assert any(f.get("event") == "media" for f in sent)


def test_tts_stream_ulaw_frames_are_valid():
    from app.providers.tts import TTSProvider
    chunks = b"".join(TTSProvider("local").stream_ulaw("hello there friend"))
    # mu-law is 1 byte/sample; decoding to PCM16 doubles the size
    pcm = audioop.ulaw2lin(chunks, 2)
    assert len(pcm) == len(chunks) * 2 and len(chunks) > 0
