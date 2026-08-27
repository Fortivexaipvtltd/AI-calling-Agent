from __future__ import annotations

import time
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import settings
from ..observability.logging import log, request_id_ctx
from ..observability.metrics import metrics
from .rate_limit import build_limiter

_limiter = build_limiter()

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "X-XSS-Protection": "0",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
}

# Paths that skip auth/rate-limit accounting noise but still get headers.
_OPEN_PATHS = {"/health", "/ready", "/metrics", "/", "/docs", "/openapi.json", "/redoc"}


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request_id_ctx.set(rid)
        start = time.perf_counter()

        # Body-size cap (defence against oversized payloads).
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > settings.max_body_bytes:
            return self._json(413, "payload_too_large", rid)

        # Rate limit (skip open/infra paths).
        if settings.rate_limit_enabled and request.url.path not in _OPEN_PATHS:
            key = request.headers.get("x-api-key") or (request.client.host if request.client else "anon")
            ok, retry = _limiter.allow(key)
            if not ok:
                metrics.inc("http_rate_limited_total")
                resp = self._json(429, "rate_limited", rid)
                resp.headers["Retry-After"] = str(retry)
                return resp

        try:
            response = await call_next(request)
        except Exception:
            latency = (time.perf_counter() - start) * 1000
            metrics.inc("http_requests_total", method=request.method, status="500")
            metrics.observe_latency(latency)
            log.exception("request_error", extra={"method": request.method,
                          "path": request.url.path, "status": 500,
                          "latency_ms": round(latency, 1)})
            raise

        latency = (time.perf_counter() - start) * 1000
        metrics.inc("http_requests_total", method=request.method,
                    status=str(response.status_code))
        metrics.observe_latency(latency)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        response.headers["X-Request-ID"] = rid
        log.info("request", extra={"method": request.method, "path": request.url.path,
                 "status": response.status_code, "latency_ms": round(latency, 1),
                 "client": request.client.host if request.client else "-"})
        return response

    @staticmethod
    def _json(status: int, code: str, rid: str) -> JSONResponse:
        return JSONResponse(status_code=status,
                            content={"ok": False, "error": {"code": code}, "request_id": rid},
                            headers={"X-Request-ID": rid})
