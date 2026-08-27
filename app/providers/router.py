from __future__ import annotations

import json
import urllib.request

from ..config import settings
from .llm import LLMResponder
from .stt import STTProvider
from .tts import TTSProvider

# Which env key gates each named provider. Empty string => always available (local).
_LLM_KEYS = {"local": "", "anthropic": settings.anthropic_api_key,
             "openai": settings.byo_api_key, "azure": settings.byo_api_key,
             "google": settings.byo_api_key, "byo": settings.byo_api_key}
_STT_KEYS = {"local": "", "deepgram": settings.stt_api_key,
             "whisper": settings.byo_api_key, "google": settings.byo_api_key}
_TTS_KEYS = {"local": "", "elevenlabs": settings.tts_api_key,
             "cartesia": settings.tts_api_key, "azure": settings.tts_api_key}


def _chain(route: str) -> list[str]:
    return [p.strip() for p in route.split(",") if p.strip()]


class ModelRouter:
    """Picks the first configured provider in each modality's route, with the
    local engine as the guaranteed tail. BYO: any OpenAI-compatible base URL +
    key works for LLM/STT without code changes.
    """

    def resolve(self, modality: str) -> str:
        route, keys = {
            "llm": (settings.llm_route, _LLM_KEYS),
            "stt": (settings.stt_route, _STT_KEYS),
            "tts": (settings.tts_route, _TTS_KEYS),
        }[modality]
        for provider in _chain(route):
            if provider == "local" or keys.get(provider):
                return provider
        return "local"

    def plan(self) -> dict:
        return {m: self.resolve(m) for m in ("llm", "stt", "tts")}

    # ---- modality factories ---------------------------------------------
    def llm(self) -> LLMResponder:
        provider = self.resolve("llm")
        if provider in ("openai", "azure", "google", "byo") and settings.byo_base_url:
            return _BYOResponder()
        # local + anthropic share the existing responder.
        return LLMResponder("anthropic" if provider == "anthropic" else "local")

    def stt(self) -> STTProvider:
        provider = self.resolve("stt")
        return STTProvider("deepgram" if provider == "deepgram" else "local")

    def tts(self, voice: str = "nova") -> TTSProvider:
        provider = self.resolve("tts")
        return TTSProvider("elevenlabs" if provider == "elevenlabs" else "local", voice=voice)


class _BYOResponder(LLMResponder):
    """Bring-your-own OpenAI-compatible chat endpoint. Falls back to local."""

    def __init__(self) -> None:
        super().__init__(provider="byo")

    def word(self, *, intent, lead, product, memory_facts, objection, lead_text, history) -> str:
        try:
            return self._byo(intent, lead, product, objection, lead_text, history)
        except Exception:
            return self._local(intent, lead, product, memory_facts, objection, lead_text)

    def _byo(self, intent, lead, product, objection, lead_text, history) -> str:
        from .llm import GUARDRAILS, INTENT_GOAL
        system = (f"{GUARDRAILS}\nAPPROVED FACTS: {product.get('name','')} / "
                  f"{product.get('outcomes',[])} / {product.get('guarantee','')}.\n"
                  f"GOAL: {INTENT_GOAL.get(intent, 'Move the sale forward.')}")
        msgs = [{"role": "system", "content": system}]
        for m in history[-8:]:
            if m.get("text"):
                msgs.append({"role": "assistant" if m["role"] == "agent" else "user",
                             "content": m["text"]})
        msgs.append({"role": "user", "content": lead_text or "(call connected)"})
        body = json.dumps({"model": settings.byo_model or "gpt-4o-mini",
                           "max_tokens": 120, "messages": msgs}).encode()
        req = urllib.request.Request(
            settings.byo_base_url.rstrip("/") + "/chat/completions", data=body,
            headers={"content-type": "application/json",
                     "authorization": f"Bearer {settings.byo_api_key}"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"].strip()


router = ModelRouter()
