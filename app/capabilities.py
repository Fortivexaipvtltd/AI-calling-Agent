from __future__ import annotations

"""Single source of truth for every primitive the platform claims to support.

`GET /v1/capabilities` and `python -m scripts.check_capabilities` both read this,
so "is X added?" has one honest answer instead of a guess. Each entry names the
module that implements it and, where relevant, the REST surface.
"""

# name -> (category, module path, rest surface or "")
CAPABILITIES: dict[str, tuple[str, str, str]] = {
    # ---- telephony / voice transport ------------------------------------
    "inbound": ("telephony", "app.telephony.inbound", "POST /v1/telephony/inbound"),
    "outbound": ("telephony", "app.providers.telephony", "POST /v1/calls"),
    "pstn": ("telephony", "app.providers.telephony", ""),
    "sip": ("telephony", "app.telephony.sip", "POST /v1/telephony/sip/trunks"),
    "webrtc": ("telephony", "app.telephony.webrtc", "POST /v1/telephony/webrtc/offer"),
    "browser_calling": ("telephony", "app.telephony.webrtc", "POST /v1/telephony/webrtc/offer"),
    "phone_numbers": ("telephony", "app.telephony.numbers", "POST /v1/telephony/numbers"),
    "number_pools": ("telephony", "app.telephony.numbers", "POST /v1/telephony/number-pools"),
    "call_transfer": ("telephony", "app.telephony.transfer", "POST /v1/calls/{id}/transfer"),
    "warm_transfer": ("telephony", "app.telephony.transfer", "POST /v1/calls/{id}/warm-transfer"),
    "cold_transfer": ("telephony", "app.telephony.transfer", "POST /v1/calls/{id}/cold-transfer"),
    "conference": ("telephony", "app.telephony.transfer", "POST /v1/telephony/conference"),
    "voicemail": ("telephony", "app.telephony.amd", "POST /v1/telephony/voicemail-drop"),
    "dtmf": ("telephony", "app.telephony.ivr", "POST /v1/telephony/dtmf"),
    "ivr": ("telephony", "app.telephony.ivr", "POST /v1/telephony/ivr/run"),
    "call_queues": ("telephony", "app.telephony.queues", "POST /v1/telephony/queues"),
    "call_recording": ("telephony", "app.telephony.recording", "POST /v1/calls/{id}/record"),
    "transcription": ("voice", "app.providers.stt", "POST /v1/voice/listen"),
    "real_time_transcription": ("voice", "app.realtime.stt", ""),
    "interruption": ("voice", "app.realtime.session_manager", ""),
    "barge_in": ("voice", "app.realtime.session_manager", ""),
    "vad": ("voice", "app.realtime.vad", ""),
    "turn_detection": ("voice", "app.realtime.turn_detection", ""),
    "noise_suppression": ("voice", "app.realtime.audio", ""),
    "echo_cancellation": ("voice", "app.realtime.audio", ""),
    "codec_support": ("voice", "app.realtime.audio", ""),
    "natural_prosody": ("voice", "app.realtime.prosody", "POST /v1/voice/say"),
    "streaming_low_latency": ("voice", "app.realtime.streaming", "POST /v1/voice/say"),
    "adaptive_turn_taking": ("voice", "app.realtime.turntaking", "POST /v1/voice/turn-taking"),
    "streaming_tts": ("voice", "app.providers.tts", ""),
    "bidirectional_media": ("voice", "app.realtime.pipeline", "WS /v1/telephony/twilio/media/{call_id}"),
    "call_retry": ("telephony", "app.telephony.retry", ""),
    "voicemail_detection": ("telephony", "app.telephony.amd", ""),
    "answering_machine_detection": ("telephony", "app.telephony.amd", ""),
    # ---- ai ---------------------------------------------------------------
    "multiple_llms": ("ai", "app.providers.router", ""),
    "multiple_stt": ("ai", "app.providers.router", ""),
    "multiple_tts": ("ai", "app.providers.router", ""),
    "byo_model": ("ai", "app.providers.router", ""),
    "byo_api": ("ai", "app.providers.router", ""),
    "model_routing": ("ai", "app.providers.router", "GET /v1/providers/route"),
    "rag": ("ai", "app.ai.rag", "POST /v1/rag/search"),
    "tools": ("ai", "app.tools.registry", "GET /v1/tools"),
    "function_calling": ("ai", "app.tools.registry", "POST /v1/tools/call"),
    "mcp": ("ai", "app.ai.mcp", "POST /v1/mcp/call"),
    "memory": ("ai", "app.agent_runtime.memory", "GET /v1/leads/{id}/facts"),
    "structured_outputs": ("ai", "app.ai.structured", "POST /v1/ai/structured"),
    "workflows": ("ai", "app.ai.workflows", "POST /v1/workflows/run"),
    "multi_agent": ("ai", "app.ai.multi_agent", "POST /v1/squads/run"),
    "agent_handoff": ("ai", "app.ai.multi_agent", ""),
    "human_handoff": ("ai", "app.agent_runtime.handoff", "POST /v1/calls/{id}/transfer"),
    "dynamic_prompts": ("ai", "app.ai.prompts", ""),
    "contextual_instructions": ("ai", "app.ai.prompts", ""),
    # ---- business ---------------------------------------------------------
    "crm": ("business", "app.tools.registry", "GET /v1/leads/{id}/activities"),
    "calendar": ("business", "app.tools.registry", "POST /v1/calendar/book"),
    "email": ("business", "app.tools.registry", ""),
    "sms": ("business", "app.tools.registry", ""),
    "whatsapp": ("business", "app.business.whatsapp", "POST /v1/whatsapp/send"),
    "payments": ("business", "app.tools.registry", "POST /v1/webhooks/payment"),
    "lead_management": ("business", "app.main", "GET /v1/leads"),
    "campaigns": ("business", "app.main", "GET /v1/campaigns"),
    "analytics": ("business", "app.main", "GET /v1/analytics/funnel"),
    "reporting": ("business", "app.business.reporting", "GET /v1/reports/{name}"),
    "webhooks": ("business", "app.main", "POST /v1/webhooks/telephony"),
    "api": ("business", "app.main", "GET /health"),
    "sdks": ("business", "app.business.sdk", ""),
    "billing": ("business", "app.business.billing", "GET /v1/billing/invoice"),
    "usage": ("business", "app.business.billing", "GET /v1/usage"),
    "teams": ("business", "app.business.teams", "POST /v1/teams"),
    "rbac": ("business", "app.business.teams", ""),
    # ---- advanced capabilities -------------------------------------------
    "realtime_voice_engine": ("advanced", "app.advanced.realtime_engine", ""),
    "multimodal_runtime": ("advanced", "app.advanced.multimodal_runtime", "POST /v1/runtime/step"),
    "memory_graph": ("advanced", "app.advanced.memory_graph", "GET /v1/memory-graph/{lead_id}"),
    "autonomous_execution": ("advanced", "app.advanced.autonomous_executor", "POST /v1/autonomy/run"),
    "conversation_intelligence": ("advanced", "app.advanced.conversation_intelligence", ""),
    "simulation_evaluation_redteam": ("advanced", "app.advanced.evaluation", "POST /v1/eval/run"),
    "model_provider_voice_optimization": ("advanced", "app.advanced.optimizer", "POST /v1/optimize"),
    "computer_use": ("advanced", "app.advanced.computer_use", "POST /v1/computer-use/run"),
    "workforce_orchestration": ("advanced", "app.advanced.workforce", "POST /v1/workforce/dispatch"),
    "autonomous_business_optimization": ("advanced", "app.advanced.business_optimizer", "POST /v1/business/optimize"),
}


def _importable(module_path: str) -> bool:
    import importlib

    try:
        importlib.import_module(module_path)
        return True
    except Exception:
        return False


def audit() -> dict:
    """Return coverage: which capabilities resolve to a real, importable module."""
    rows = []
    present = 0
    for name, (cat, mod, rest) in sorted(CAPABILITIES.items()):
        ok = _importable(mod)
        present += ok
        rows.append({"capability": name, "category": cat, "module": mod,
                     "rest": rest, "present": ok})
    total = len(CAPABILITIES)
    return {"total": total, "present": present, "missing": total - present,
            "coverage": round(present / total, 3), "items": rows}
