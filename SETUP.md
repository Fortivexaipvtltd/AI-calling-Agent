# SETUP — going live

The app runs out of the box in demo mode (SQLite, local voice engines, text
simulation). To make real calls with persistent data, do these in order.

## 1. Persistent database (Postgres)
```
cp .env.example .env
docker compose up --build     # starts app + Postgres, runs migrations automatically
```
Data now survives restarts. (SQLite is only for local demo.)

## 2. Provider accounts → keys in .env
| Provider | Sign up | Put in .env |
|----------|---------|-------------|
| Twilio | twilio.com — buy a voice number | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` |
| Deepgram | deepgram.com | `STT_PROVIDER=deepgram`, `STT_API_KEY` |
| ElevenLabs | elevenlabs.com — pick a friendly voice | `TTS_PROVIDER=elevenlabs`, `TTS_API_KEY`, `TTS_VOICE_ID` |
| LLM | Anthropic (or BYO) | `ANTHROPIC_API_KEY` (or `BYO_*`) |

## 3. Make your server reachable by Twilio
Set `PUBLIC_BASE_URL` to your HTTPS address.
- Testing: `ngrok http 8000` → use the https URL it prints.
- Production: your deployed domain.

## 4. Point the Twilio number at the app
In the Twilio console, set the number's **Voice webhook** (A call comes in) to:
```
POST  {PUBLIC_BASE_URL}/v1/telephony/twilio/answer/{call_id}
```
Outbound calls placed via `POST /v1/telephony/dial` set this automatically.

## 5. Tune the voice by ear
```
TTS_PROVIDER=elevenlabs TTS_API_KEY=... python -m scripts.voice_preview
```
Listen to `voice_samples/<preset>/*.mp3`, then edit `app/realtime/voice_profile.py`
(pause lengths, rate, pitch, stability/style) or set `VOICE_PROFILE` /
`VOICE_OVERRIDES`.

## 6. Use the console
Open `{PUBLIC_BASE_URL}/` — Dashboard, Leads (add / CSV / web-form), AI Calling
(live transcript + pipeline + transfer), Call History, Follow-ups, Agents,
Simulator, Settings (shows which integrations are connected).

Where leads come from: `POST /v1/leads/import`, the CSV upload, or the public
`POST /v1/intake/web-form` (wire your website/ad form to it).

## Production hardening (before real traffic)
Set `APP_ENV=production`, `AUTH_ENABLED=1`, `RBAC_ENABLED=1`, real `API_KEYS`,
explicit `CORS_ORIGINS`/`TRUSTED_HOSTS`, `REDIS_URL` for multi-instance rate
limiting. See `PRODUCTION.md` for the full checklist.
