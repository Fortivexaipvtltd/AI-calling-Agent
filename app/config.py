from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv
load_dotenv()


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)

@dataclass
class Settings:
    app_name: str = "Highh Human Sales Agent"
    env: str = _env("APP_ENV", "development")
    database_url: str = _env("DATABASE_URL", "sqlite:///:memory:")
    redis_url: str = _env("REDIS_URL", "memory://")

    # LLM / voice provider stubs (deterministic local engines by default)
    llm_provider: str = _env("LLM_PROVIDER", "local")  # local | anthropic | byo
    llm_model: str = _env("LLM_MODEL", "claude-sonnet-4-6")
    anthropic_api_key: str = _env("ANTHROPIC_API_KEY", "")
    stt_provider: str = _env("STT_PROVIDER", "local")  # local | deepgram
    stt_api_key: str = _env("STT_API_KEY", "")
    tts_provider: str = _env("TTS_PROVIDER", "local")  # local | elevenlabs
    tts_api_key: str = _env("TTS_API_KEY", "")
    tts_voice_id: str = _env("TTS_VOICE_ID", "")
    telephony_provider: str = _env("TELEPHONY_PROVIDER", "local")  # local | twilio | exotel
    exotel_sid: str = _env("EXOTEL_SID", "")
    exotel_api_key: str = _env("EXOTEL_API_KEY", "")
    exotel_api_token: str = _env("EXOTEL_API_TOKEN", "")
    exotel_caller_id: str = _env("EXOTEL_CALLER_ID", "")
    exotel_subdomain: str = _env("EXOTEL_SUBDOMAIN", "api.exotel.com")
    exotel_region: str = _env("EXOTEL_REGION", "in")  # in | sg | us
    exotel_flow_app_id: str = _env("EXOTEL_FLOW_APP_ID", "")  # App Bazaar flow (voicebot)
    twilio_account_sid: str = _env("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = _env("TWILIO_AUTH_TOKEN", "")
    twilio_from_number: str = _env("TWILIO_FROM_NUMBER", "")

    # Automatic follow-up scheduler
    scheduler_enabled: bool = _env("SCHEDULER_ENABLED", "1") == "1"
    scheduler_interval_seconds: int = int(_env("SCHEDULER_INTERVAL_SECONDS", "30"))

    # Compliance
    call_window_start_hour: int = int(_env("CALL_WINDOW_START_HOUR", "9"))
    call_window_end_hour: int = int(_env("CALL_WINDOW_END_HOUR", "20"))
    max_attempts_per_lead: int = int(_env("MAX_ATTEMPTS_PER_LEAD", "5"))

    # Runtime
    turn_silence_ms: int = int(_env("TURN_SILENCE_MS", "700"))
    max_response_chars: int = int(_env("MAX_RESPONSE_CHARS", "240"))

    default_org_id: str = "org_default"

    voices: list[str] = field(default_factory=lambda: ["nova", "aarav", "meera"])

    # ---- extended telephony transport -----------------------------------
    sip_provider: str = _env("SIP_PROVIDER", "local")        # local | twilio_sip | telnyx
    sip_domain: str = _env("SIP_DOMAIN", "sip.local")
    webrtc_provider: str = _env("WEBRTC_PROVIDER", "local")  # local | livekit | daily
    webrtc_ice_servers: str = _env("WEBRTC_ICE_SERVERS", "stun:stun.l.google.com:19302")
    recording_enabled: bool = _env("RECORDING_ENABLED", "1") == "1"
    recording_store: str = _env("RECORDING_STORE", "memory://recordings")
    amd_enabled: bool = _env("AMD_ENABLED", "1") == "1"
    default_codec: str = _env("DEFAULT_CODEC", "opus")       # opus | pcmu | pcma | g722
    noise_suppression: bool = _env("NOISE_SUPPRESSION", "1") == "1"
    echo_cancellation: bool = _env("ECHO_CANCELLATION", "1") == "1"
    max_retries_per_lead: int = int(_env("MAX_RETRIES_PER_LEAD", "3"))
    retry_backoff_minutes: int = int(_env("RETRY_BACKOFF_MINUTES", "60"))

    # ---- campaign dialer ------------------------------------------------
    dialer_max_concurrent: int = int(_env("DIALER_MAX_CONCURRENT", "5"))
    dialer_calls_per_min: int = int(_env("DIALER_CALLS_PER_MIN", "20"))
    dialer_default_timezone: str = _env("DIALER_TIMEZONE", "Asia/Kolkata")

    # ---- model routing / BYO --------------------------------------------
    # comma-separated provider preference lists; router tries left to right.
    llm_route: str = _env("LLM_ROUTE", "local,anthropic,openai,azure,google")
    stt_route: str = _env("STT_ROUTE", "local,deepgram,whisper,google")
    tts_route: str = _env("TTS_ROUTE", "local,elevenlabs,cartesia,azure")
    byo_base_url: str = _env("BYO_BASE_URL", "")             # OpenAI-compatible endpoint
    byo_api_key: str = _env("BYO_API_KEY", "")
    byo_model: str = _env("BYO_MODEL", "")
    byo_protocol: str = _env("BYO_PROTOCOL", "auto")  # auto | gemini | openai | anthropic

    # ---- channels -------------------------------------------------------
    whatsapp_provider: str = _env("WHATSAPP_PROVIDER", "local")   # local | meta | twilio
    whatsapp_token: str = _env("WHATSAPP_TOKEN", "")
    whatsapp_phone_id: str = _env("WHATSAPP_PHONE_ID", "")

    # ---- SMS + email (omnichannel follow-ups) ---------------------------
    sms_provider: str = _env("SMS_PROVIDER", "local")             # local | twilio
    sms_from: str = _env("SMS_FROM", "")
    email_provider: str = _env("EMAIL_PROVIDER", "local")         # local | smtp
    smtp_host: str = _env("SMTP_HOST", "")
    smtp_port: int = int(_env("SMTP_PORT", "587"))
    smtp_user: str = _env("SMTP_USER", "")
    smtp_password: str = _env("SMTP_PASSWORD", "")
    email_from: str = _env("EMAIL_FROM", "admissions@example.com")
    brochure_url: str = _env("BROCHURE_URL", "https://example.com/brochure.pdf")

    # ---- ai extras ------------------------------------------------------
    mcp_servers: str = _env("MCP_SERVERS", "")               # comma-separated base URLs
    rag_top_k: int = int(_env("RAG_TOP_K", "4"))

    # ---- analytics cost model (per-call, USD) ---------------------------
    cost_twilio_per_min: float = float(_env("COST_TWILIO_PER_MIN", "0.014"))
    cost_stt_per_min: float = float(_env("COST_STT_PER_MIN", "0.0043"))
    cost_tts_per_min: float = float(_env("COST_TTS_PER_MIN", "0.03"))
    cost_llm_per_call: float = float(_env("COST_LLM_PER_CALL", "0.01"))

    # ---- calendar (real bookings) --------------------------------------
    calendar_provider: str = _env("CALENDAR_PROVIDER", "local")  # local | google | outlook
    calendar_token: str = _env("CALENDAR_TOKEN", "")
    calendar_id: str = _env("CALENDAR_ID", "primary")

    # ---- payments (in-call enrollment) ----------------------------------
    payment_provider: str = _env("PAYMENT_PROVIDER", "local")    # local | razorpay
    razorpay_key_id: str = _env("RAZORPAY_KEY_ID", "")
    razorpay_key_secret: str = _env("RAZORPAY_KEY_SECRET", "")
    payment_amount_inr: int = int(_env("PAYMENT_AMOUNT_INR", "50000"))

    # ---- RAG embeddings -------------------------------------------------
    embeddings_provider: str = _env("EMBEDDINGS_PROVIDER", "local")  # local | openai | voyage
    embeddings_api_key: str = _env("EMBEDDINGS_API_KEY", "")
    embeddings_model: str = _env("EMBEDDINGS_MODEL", "text-embedding-3-small")

    # ---- monitoring / alerts --------------------------------------------
    alert_webhook_url: str = _env("ALERT_WEBHOOK_URL", "")       # Slack/webhook
    alert_latency_ms: int = int(_env("ALERT_LATENCY_MS", "1500"))
    alert_cost_per_call_usd: float = float(_env("ALERT_COST_PER_CALL_USD", "0.5"))

    # ---- billing / rbac -------------------------------------------------
    price_per_call_minute_inr: float = float(_env("PRICE_PER_CALL_MINUTE_INR", "3.0"))
    price_per_llm_1k_tokens_inr: float = float(_env("PRICE_PER_LLM_1K_TOKENS_INR", "1.5"))
    rbac_enabled: bool = _env("RBAC_ENABLED", "0") == "1"    # off by default for local dev
    codecs: list[str] = field(default_factory=lambda: ["opus", "pcmu", "pcma", "g722"])

    # ---- production: security / auth ------------------------------------
    auth_enabled: bool = _env("AUTH_ENABLED", "0") == "1"    # off for local/tests, on in prod
    api_keys: str = _env("API_KEYS", "")                     # comma-separated raw keys (dev)
    api_key_hashes: str = _env("API_KEY_HASHES", "")         # comma-separated sha256 (prod)
    cors_origins: str = _env("CORS_ORIGINS", "*")            # allowlist in prod, never * with creds
    trusted_hosts: str = _env("TRUSTED_HOSTS", "*")
    rate_limit_per_min: int = int(_env("RATE_LIMIT_PER_MIN", "120"))
    rate_limit_enabled: bool = _env("RATE_LIMIT_ENABLED", "1") == "1"
    max_body_bytes: int = int(_env("MAX_BODY_BYTES", str(1024 * 1024)))  # 1 MiB

    # ---- production: database / ops -------------------------------------
    db_pool_size: int = int(_env("DB_POOL_SIZE", "5"))
    db_max_overflow: int = int(_env("DB_MAX_OVERFLOW", "10"))
    db_pool_timeout: int = int(_env("DB_POOL_TIMEOUT", "30"))
    log_level: str = _env("LOG_LEVEL", "INFO")
    log_json: bool = _env("LOG_JSON", "1") == "1"

    # ---- telephony webhooks / media -------------------------------------
    # Public HTTPS base URL of this service, used to build Twilio answer,
    # status and Media Stream (wss) callback URLs. Required for live calls.
    public_base_url: str = _env("PUBLIC_BASE_URL", "")
    validate_twilio_signature: bool = _env("VALIDATE_TWILIO_SIGNATURE", "1") == "1"

    @property
    def is_production(self) -> bool:
        return self.env.lower() in ("prod", "production")

    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def trusted_host_list(self) -> list[str]:
        return [h.strip() for h in self.trusted_hosts.split(",") if h.strip()] or ["*"]

    def validate(self) -> list[str]:
        """Fail-fast checks. Returns a list of fatal problems (empty == ok)."""
        problems: list[str] = []
        if self.is_production:
            if not self.auth_enabled:
                problems.append("AUTH_ENABLED must be 1 in production")
            if self.auth_enabled and not (self.api_keys or self.api_key_hashes):
                problems.append("no API_KEYS/API_KEY_HASHES configured while auth is on")
            if "*" in self.cors_list():
                problems.append("CORS_ORIGINS must be an explicit allowlist in production")
            if self.database_url.startswith("sqlite"):
                problems.append("SQLite is not supported in production; set a Postgres DATABASE_URL")
        return problems


settings = Settings()
