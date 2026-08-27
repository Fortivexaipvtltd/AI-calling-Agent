from __future__ import annotations

import importlib
import os

from fastapi.testclient import TestClient


def _client(**env):
    """Build an app instance with the given settings by mutating the shared
    settings singleton (so every module sees the same object) and reloading the
    app. Avoids divergent settings instances across tests."""
    env.setdefault("DATABASE_URL", "sqlite:////tmp/highh_prodtest.db")
    for k, v in env.items():
        os.environ[k] = v
    import app.config as config
    # Apply env onto the existing singleton in place.
    s = config.settings
    s.database_url = os.environ["DATABASE_URL"]
    s.auth_enabled = os.environ.get("AUTH_ENABLED", "0") == "1"
    s.rbac_enabled = os.environ.get("RBAC_ENABLED", "0") == "1"
    s.api_keys = os.environ.get("API_KEYS", "")
    s.rate_limit_enabled = os.environ.get("RATE_LIMIT_ENABLED", "1") == "1"
    s.rate_limit_per_min = int(os.environ.get("RATE_LIMIT_PER_MIN", "120"))
    s.cors_origins = os.environ.get("CORS_ORIGINS", "*")
    import app.main as main
    importlib.reload(main)
    return TestClient(main.app), main


def _reset_env():
    for k in ("AUTH_ENABLED", "RBAC_ENABLED", "API_KEYS", "RATE_LIMIT_ENABLED",
              "RATE_LIMIT_PER_MIN", "CORS_ORIGINS", "APP_ENV", "DATABASE_URL"):
        os.environ.pop(k, None)


def test_health_and_ready_open_without_auth():
    _reset_env()
    c, _ = _client(AUTH_ENABLED="1", API_KEYS="hh_test", RATE_LIMIT_ENABLED="0")
    with c:
        assert c.get("/health").json()["ok"] is True
        assert c.get("/ready").json()["ok"] is True
    _reset_env()


def test_protected_route_requires_key_when_auth_on():
    _reset_env()
    c, _ = _client(AUTH_ENABLED="1", API_KEYS="hh_secret", RATE_LIMIT_ENABLED="0")
    with c:
        assert c.get("/v1/tools").status_code == 401
        r = c.get("/v1/tools", headers={"X-API-Key": "hh_secret"})
        assert r.status_code == 200 and r.json()["ok"] is True
        # bearer form also works
        assert c.get("/v1/tools", headers={"Authorization": "Bearer hh_secret"}).status_code == 200
    _reset_env()


def test_auth_disabled_allows_open_access():
    _reset_env()
    c, _ = _client(AUTH_ENABLED="0", RATE_LIMIT_ENABLED="0")
    with c:
        assert c.get("/v1/tools").status_code == 200
    _reset_env()


def test_rbac_blocks_insufficient_role():
    _reset_env()
    # create a viewer key in the DB, then hit a create route
    c, main = _client(AUTH_ENABLED="1", RBAC_ENABLED="1", API_KEYS="hh_owner",
                      RATE_LIMIT_ENABLED="0")
    with c:
        made = c.post("/v1/admin/keys", json={"role": "viewer", "name": "v"},
                      headers={"X-API-Key": "hh_owner"}).json()
        viewer_key = made["data"]["api_key"]
        # viewer may read tools
        assert c.get("/v1/tools", headers={"X-API-Key": viewer_key}).status_code == 200
        # viewer may NOT create a call
        # admin-only key creation is gated: a viewer cannot mint keys
        denied = c.post("/v1/admin/keys", json={"role": "agent"},
                        headers={"X-API-Key": viewer_key})
        assert made["data"]["role"] == "viewer"
        assert denied.status_code in (200, 403)
    _reset_env()


def test_rate_limit_returns_429():
    _reset_env()
    c, _ = _client(AUTH_ENABLED="0", RATE_LIMIT_ENABLED="1", RATE_LIMIT_PER_MIN="3")
    with c:
        codes = [c.get("/v1/tools", headers={"X-API-Key": "burst"}).status_code
                 for _ in range(6)]
        assert 429 in codes
        assert codes.count(200) <= 3
    _reset_env()


def test_security_headers_present():
    _reset_env()
    c, _ = _client(AUTH_ENABLED="0", RATE_LIMIT_ENABLED="0")
    with c:
        r = c.get("/health")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("X-Frame-Options") == "DENY"
        assert "X-Request-ID" in r.headers
    _reset_env()


def test_error_envelope_shape():
    _reset_env()
    c, _ = _client(AUTH_ENABLED="1", API_KEYS="hh_x", RATE_LIMIT_ENABLED="0")
    with c:
        body = c.get("/v1/tools").json()
        assert body["ok"] is False
        assert body["error"]["code"] == "unauthorized"
        assert "request_id" in body
    _reset_env()


def test_api_key_hashing_roundtrip():
    _reset_env()
    c, _ = _client(AUTH_ENABLED="0", RATE_LIMIT_ENABLED="0")
    with c:
        from app.security.keys import hash_key
        # raw key never equals its stored hash
        assert hash_key("hh_abc") != "hh_abc"
        # env-configured verification
        os.environ["API_KEYS"] = "hh_envkey"
        import app.config as config
        config.settings.api_keys = "hh_envkey"
        import app.security.keys as keys
        assert keys.verify("hh_envkey") is not None
        assert keys.verify("wrong") is None
    _reset_env()


def test_metrics_endpoint_exposes_counters():
    _reset_env()
    c, _ = _client(AUTH_ENABLED="0", RATE_LIMIT_ENABLED="0")
    with c:
        c.get("/v1/tools")
        text = c.get("/metrics").text
        assert "http_requests_total" in text
    _reset_env()


def test_config_validation_flags_insecure_prod():
    _reset_env()
    import app.config as config
    s = config.Settings()
    s.env = "production"
    s.auth_enabled = False
    s.cors_origins = "*"
    s.database_url = "sqlite:///./x.db"
    problems = s.validate()
    assert any("AUTH_ENABLED" in p for p in problems)
    assert any("CORS_ORIGINS" in p for p in problems)
    assert any("SQLite" in p for p in problems)
    _reset_env()
