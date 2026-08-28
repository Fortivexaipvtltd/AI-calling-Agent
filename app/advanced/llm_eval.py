from __future__ import annotations

import time

from ..config import settings

# Lightweight, deterministic evaluation of the agent: does it stay grounded
# (no invented guarantees/prices), how fast does it respond, and what does a
# turn cost. Runs without external judges so it works in CI.

_HALLUCINATION_MARKERS = (
    "guaranteed job", "assured placement", "100% job", "guaranteed placement",
    "50% off", "free laptop", "lifetime access guaranteed",
)


def score_turn(agent_text: str, *, grounded: bool | None = None) -> dict:
    text = (agent_text or "").lower()
    hallucinated = any(m in text for m in _HALLUCINATION_MARKERS)
    # Quality heuristics: non-empty, not too long, asks/advances the conversation.
    length_ok = 3 <= len(agent_text.split()) <= 60
    quality = 1.0
    if not agent_text.strip():
        quality = 0.0
    elif not length_ok:
        quality -= 0.3
    if hallucinated:
        quality -= 0.7
    if grounded is False and "?" in agent_text:
        quality += 0.0  # asking to confirm is fine
    return {"hallucinated": hallucinated, "quality": round(max(0.0, quality), 3),
            "length_ok": length_ok}


def cost_of(minutes: float) -> float:
    s = settings
    return round(minutes * (s.cost_twilio_per_min + s.cost_stt_per_min
                            + s.cost_tts_per_min) + s.cost_llm_per_call, 4)


def evaluate_sample(runtime_factory, scripts: list[list[str]]) -> dict:
    """Run sample conversations, scoring hallucination/quality/latency/cost."""
    turns = 0
    hallucinations = 0
    quality_sum = 0.0
    latencies: list[float] = []
    for script in scripts:
        rt = runtime_factory()
        rt.open()
        for line in script:
            t0 = time.perf_counter()
            turn = rt.handle(line)
            latencies.append((time.perf_counter() - t0) * 1000)
            s = score_turn(turn.agent_text)
            turns += 1
            hallucinations += 1 if s["hallucinated"] else 0
            quality_sum += s["quality"]
            if turn.ended:
                break
    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0.0
    avg_min = 1.5
    return {
        "turns": turns,
        "hallucination_rate": round(hallucinations / turns, 3) if turns else 0.0,
        "avg_quality": round(quality_sum / turns, 3) if turns else 0.0,
        "latency_ms_avg": round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
        "latency_ms_p95": round(p95, 1),
        "est_cost_per_call_usd": cost_of(avg_min),
        "passed": (hallucinations == 0 and (quality_sum / turns if turns else 0) >= 0.6),
    }
