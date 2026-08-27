# Production readiness

Honest status of each layer. "Proven" = exercised by automated tests or a live
smoke in this repo. "Code-complete" = correct integration written, but only
validated against mocks — it needs real credentials + live testing before it
carries production traffic.

## Ready and proven (in this repo)

| Area | Status | Evidence |
|------|--------|----------|
| AuthN (API keys, bearer/X-API-Key, hashed at rest) | Proven | `tests/test_production.py` |
| AuthZ (RBAC roles + `require(permission)`) | Proven | `tests/test_production.py` |
| Rate limiting (in-process; Redis-capable) | Proven (in-proc) | `tests/test_production.py` |
| Security headers, request-id, error envelope, body cap | Proven | `tests/test_production.py` |
| CORS allowlist + trusted hosts + fail-fast prod config | Proven | `tests/test_production.py` |
| Structured JSON logging, `/health`, `/ready`, `/metrics` | Proven | live smoke |
| Postgres pooling + Alembic migrations (chain applies clean) | Proven | `alembic upgrade head` |
| Durable call state (survives worker loss / restart) | Proven | `tests/test_durability.py` |
| Twilio signature validation on webhooks | Proven | `tests/test_telephony_live.py` |
| Twilio answer TwiML + Media Stream wiring | Proven (shape) | live smoke |
| Twilio Media Streams WS bridge (µ-law → PCM → STT) | Proven (decode/VAD) | `tests/test_telephony_live.py` |
| Twilio outbound dial (REST, AMD, recording params) | Code-complete | mocked `urlopen` test |
| Deepgram STT (prerecorded + raw PCM params) | Code-complete | mocked `urlopen` test |
| Deepgram streaming client (WS) | Code-complete | needs `websockets` + key |
| ElevenLabs TTS | Code-complete | mocked `urlopen` test |
| Docker image + compose (app + Postgres) + CI | Code-complete | not run in CI here |

## NOT ready — needs real infrastructure, not code

These cannot be closed from inside this repo:

- **Live telephony/media traffic.** No real Twilio number, Deepgram/ElevenLabs
  account, or PSTN/WebRTC media server has been exercised. Provider code is
  correct and mock-tested; it must be validated end to end against real
  accounts, with latency/quality tuning, before serving customers.
- **Distributed scale.** The Redis limiter and durable call state make multiple
  instances *possible*, but this hasn't been load-tested. Needs a real Redis,
  horizontal-scaling test, and connection-pool sizing under load.
- **Secrets management.** Keys come from env today. Wire a secrets manager
  (AWS Secrets Manager / GCP Secret Manager / Vault) before production.
- **Backup / DR.** No automated Postgres backup, PITR, or restore drill yet.
- **Security audit.** No pentest / dependency-audit / threat model sign-off.
- **WebRTC browser calling at scale.** The signalling stub is present; a real
  media server (LiveKit/Janus) is required for production browser calls.

## Go-live checklist

1. Set `APP_ENV=production` (the app refuses to boot if auth is off, CORS is
   `*`, or the DB is SQLite).
2. Provide `DATABASE_URL` (Postgres), run `alembic upgrade head`.
3. Set `AUTH_ENABLED=1`, `RBAC_ENABLED=1`, and real `API_KEY_HASHES`.
4. Set `CORS_ORIGINS` and `TRUSTED_HOSTS` to explicit values.
5. Set `PUBLIC_BASE_URL` (HTTPS) so Twilio answer/status/media URLs resolve;
   keep `VALIDATE_TWILIO_SIGNATURE=1`.
6. Provide provider creds (`TWILIO_*`, `DEEPGRAM_API_KEY`, `ELEVENLABS_API_KEY`
   or `BYO_*`) and set `REDIS_URL` for multi-instance rate limiting.
7. Run the live-call validation against a real number in a staging project.
8. Add secrets manager, backups, monitoring/alerting, and a load test.
