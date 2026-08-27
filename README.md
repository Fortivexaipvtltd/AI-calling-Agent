# Highh Human Sales Agent

Runnable voice sales agent: state machine, agent runtime (context / policy / repair /
planner / memory / sales / handoff), tools, realtime stubs, post-call worker, compliance,
DB persistence, event bus, an automatic follow-up scheduler, pluggable LLM / TTS /
telephony providers, a simulator, and the full REST API.

Runs with zero external services (local providers). Add API keys to go live — the
providers are drop-in, no code changes.

## Run

    pip install -r requirements.txt
    python -m app.simulator.run_sim      # simulated prospect suite
    python -m tests.test_conversation    # tests
    uvicorn app.main:app --port 8000     # REST API (+ background follow-up scheduler)
    #   -> open http://localhost:8000/   for the operator console (UI)

    # Console-friendly local launch (wide calling window so live calls aren't
    # blocked by the 9pm-8am guardrail during a demo; guardrail default is unchanged):
    CALL_WINDOW_START_HOUR=0 CALL_WINDOW_END_HOUR=24 uvicorn app.main:app --port 8000

## Go live (drop-in — set env vars only)

    # Human-like wording via Claude
    export LLM_PROVIDER=anthropic
    export ANTHROPIC_API_KEY=sk-ant-...
    export LLM_MODEL=claude-sonnet-4-6

    # Real voice
    export TTS_PROVIDER=elevenlabs
    export TTS_API_KEY=...
    export TTS_VOICE_ID=...

    # Real phone calls
    export TELEPHONY_PROVIDER=twilio
    export TWILIO_ACCOUNT_SID=...
    export TWILIO_AUTH_TOKEN=...
    export TWILIO_FROM_NUMBER=+1...

If a provider key is missing or a call fails, it falls back to the local engine —
the conversation never breaks.

## What's automatic

- Every detail saved — durable facts, stage, score and probability persist after every
  turn (GET /v1/leads/{id}/facts, /v1/leads/{id}).
- Follow-up scheduled on call end — the post-call worker picks the next action and writes
  a due-dated follow-up (call / email / SMS), skipping suppressed or handed-off leads.
- Follow-up executed on time — a background scheduler runs due follow-ups (sends the
  message or re-dials), logs an activity, and runs each exactly once. Force with
  POST /v1/scheduler/tick.

## Console (UI)

A zero-build operator console is served at `/`: import leads, start a call, drive
the conversation turn by turn, and watch the state machine, score, close
probability, tool calls, insights and follow-ups update live. A Simulator tab runs
the same runtime against scripted prospects. Everything talks to the REST API only.

## Guardrails (always on)

One question per turn, short spoken replies, barge-in handling, opt-out suppression,
calling-window + attempt limits, and never inventing pricing/guarantees or promising a job
(the 180-Day guarantee is framed as continued support, subject to T&C).

## Capability coverage

Every primitive is registered in `app/capabilities.py` and verified:

    python -m scripts.check_capabilities     # prints coverage per category
    python -m tests.test_capabilities        # asserts 100% + behaviour

`GET /v1/capabilities` returns the same audit at runtime.

### Added in this build

- Telephony transport: inbound, SIP trunks, WebRTC/browser calling, phone numbers +
  number pools, warm/cold transfer, conference, IVR + DTMF, call queues, recording,
  answering-machine/voicemail detection + voicemail drop, call retry with backoff.
- Realtime DSP: noise suppression, echo cancellation, codec negotiation, full-duplex.
- AI: model/provider/voice routing + BYO endpoint, RAG, MCP client, structured
  outputs, workflow engine, multi-agent squads + agent→agent handoff, dynamic /
  contextual prompts.
- Business: WhatsApp, Python SDK, usage metering + billing/invoices, teams + RBAC,
  reporting + CSV export.
- Advanced: full-duplex realtime engine, multimodal runtime, long-term memory graph,
  autonomous multi-step executor, real-time conversation intelligence, simulation +
  evaluation + red-team, automatic model/voice optimizer (bandit), computer-use +
  API/tool execution, AI-human workforce orchestration, autonomous business optimizer.

All new modules keep the same rule: **local engine by default, real provider drop-in
via env vars, automatic fallback so the conversation never breaks.**


## Production

This build ships auth (hashed API keys, bearer/X-API-Key), RBAC, rate limiting
(Redis-capable), security headers + error envelope, structured logging,
`/health` `/ready` `/metrics`, Postgres pooling, Alembic migrations, durable
call state (survives restarts / multiple workers), and **real provider
integrations**: Twilio voice (outbound dial, answer TwiML, Media Streams WS
bridge, signature-validated status/recording webhooks, AMD), Deepgram STT
(prerecorded + streaming), and ElevenLabs TTS — each with a local fallback.

Run with Docker:

    cp .env.example .env      # fill in secrets
    docker compose up --build # app + Postgres, migrations auto-applied

Run tests + lint locally:

    pip install -r requirements-dev.txt
    ruff check app tests
    alembic upgrade head
    pytest -q

See `PRODUCTION.md` for the full readiness matrix and go-live checklist. In
short: the application + integration layers are production-grade and tested; the
live voice path is code-complete but must be validated against real Twilio /
Deepgram / ElevenLabs accounts before carrying traffic.
