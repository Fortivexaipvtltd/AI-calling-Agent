from __future__ import annotations


def test_prosody_ssml_has_prosody_pauses_and_emphasis():
    from app.realtime.prosody import ProsodyEngine
    e = ProsodyEngine()
    ssml = e.to_ssml("This is a guaranteed outcome. You start today.", intent="confirm")
    assert ssml.startswith("<speak><prosody")
    assert "<break" in ssml                    # pauses inserted
    assert "<emphasis" in ssml                 # value words emphasised
    assert "rate=" in ssml and "pitch=" in ssml


def test_prosody_normalizes_currency_and_abbreviations():
    from app.realtime.prosody import normalize_for_speech
    out = normalize_for_speech("The AI course is ₹50,000 with EMI options.")
    assert "A I" in out                        # abbreviation expanded
    assert "lakh" in out or "thousand" in out  # rupee amount spoken naturally
    assert "50,000" not in out


def test_prosody_indian_number_speech():
    from app.realtime.prosody import _speak_indian_number
    assert _speak_indian_number(50000) == "50 thousand"
    assert _speak_indian_number(150000) == "1.5 lakh"
    assert _speak_indian_number(12000000) == "1.2 crore"


def test_clause_accumulator_emits_before_full_text():
    from app.realtime.streaming import clause_accumulator
    tokens = "Hi there, I have a quick question for you today.".split()
    clauses = list(clause_accumulator(iter(tokens)))
    assert len(clauses) >= 2                    # split into multiple clauses
    assert clauses[0].endswith(",") or "Hi there" in clauses[0]


def test_streaming_voice_time_to_first_audio_beats_total():
    from app.realtime.streaming import StreamingVoice
    sv = StreamingVoice()
    res = sv.speak_text("Great news. Your plan is ready. Let's begin now.", intent="confirm")
    assert res.audio_chunks > 0
    assert res.clauses
    # first audio should arrive before the whole utterance finishes streaming
    assert res.time_to_first_audio_ms <= res.total_ms


def test_streaming_voice_barge_in_stops_early():
    from app.realtime.streaming import StreamingVoice
    sv = StreamingVoice()
    seen = {"n": 0}

    def on_audio(_chunk):
        seen["n"] += 1
        if seen["n"] == 1:
            sv.cancel()                         # interrupt right after first chunk

    res = sv.speak_text("One. Two. Three. Four. Five. Six.", on_audio=on_audio)
    assert res.barged_in is True
    assert len(res.clauses) < 6                 # did not speak the whole thing


def test_turn_taking_waits_on_incomplete_utterance():
    from app.realtime.turntaking import TurnTakingPolicy
    p = TurnTakingPolicy(base_silence_ms=500)
    # trailing conjunction -> needs longer silence, should not respond yet
    d1 = p.decide(partial_text="I was thinking that maybe we could", silence_ms=500,
                  agent_speaking=False)
    assert d1.should_respond is False
    # complete sentence + enough silence -> respond
    d2 = p.decide(partial_text="Yes, that works for me.", silence_ms=400,
                  agent_speaking=False)
    assert d2.should_respond is True
    # incomplete needs more silence than complete
    assert p.required_silence_ms("we could and") > p.required_silence_ms("okay done.")


def test_turn_taking_never_interrupts_agent():
    from app.realtime.turntaking import TurnTakingPolicy
    p = TurnTakingPolicy()
    d = p.decide(partial_text="Yes.", silence_ms=9999, agent_speaking=True)
    assert d.should_respond is False and d.reason == "agent_speaking"


def test_elevenlabs_streaming_yields_chunks(monkeypatch):
    from app import config as cfg
    from app.providers.tts import TTSProvider
    cfg.settings.tts_api_key = "el_test"

    class FakeResp:
        def __init__(self):
            self._chunks = [b"mp3-part-1", b"mp3-part-2", b""]
            self.i = 0

        def read(self, n=0):
            c = self._chunks[self.i]
            self.i += 1
            return c

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=30: FakeResp())
    chunks = list(TTSProvider("elevenlabs").synthesize_stream("hello", ssml="<speak>hi</speak>"))
    assert chunks == [b"mp3-part-1", b"mp3-part-2"]
    cfg.settings.tts_api_key = ""


def test_realtime_streaming_tts_clause_barge_in():
    from app.realtime.tts import StreamingTTS
    t = StreamingTTS()
    gen = t.stream("First clause here. Second clause here. Third clause here.")
    first = next(gen)
    assert first
    t.cancel()
    rest = list(gen)
    assert rest == []                           # cancellation stops the stream


def test_voice_profile_presets_change_pacing():
    import os

    from app.realtime import voice_profile
    os.environ["VOICE_PROFILE"] = "calm_support"
    calm = voice_profile.load_profile()
    os.environ["VOICE_PROFILE"] = "brisk_closer"
    brisk = voice_profile.load_profile()
    # calm speaks slower with longer empathy pauses than brisk
    assert calm.styles["empathy"].sentence_pause_ms > brisk.styles["empathy"].sentence_pause_ms
    assert calm.comma_pause_ms > brisk.comma_pause_ms
    os.environ.pop("VOICE_PROFILE", None)


def test_voice_overrides_apply():
    import json
    import os

    from app.realtime import voice_profile
    os.environ["VOICE_PROFILE"] = "warm_consultative"
    os.environ["VOICE_OVERRIDES"] = json.dumps(
        {"comma_pause_ms": 90, "eleven": {"style": 0.7}})
    p = voice_profile.load_profile()
    assert p.comma_pause_ms == 90 and p.eleven.style == 0.7
    os.environ.pop("VOICE_OVERRIDES", None)
    os.environ.pop("VOICE_PROFILE", None)


def test_ssml_reflects_active_profile():
    import importlib

    from app.realtime import prosody, voice_profile
    voice_profile.profile = voice_profile.PRESETS["calm_support"]()
    importlib.reload(prosody)
    ssml = prosody.ProsodyEngine().to_ssml("I understand your concern.", intent="empathize")
    assert "Take your time" in ssml         # calm preset's empathy opener
    voice_profile.profile = voice_profile.PRESETS["warm_consultative"]()
    importlib.reload(prosody)
