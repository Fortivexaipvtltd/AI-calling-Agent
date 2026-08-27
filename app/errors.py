from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .observability.logging import log, request_id_ctx


def _envelope(status: int, code: str, detail, request: Request) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"ok": False, "error": {"code": code, "detail": detail},
                 "request_id": request_id_ctx.get()},
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code = {400: "bad_request", 401: "unauthorized", 403: "forbidden",
            404: "not_found", 409: "conflict", 429: "rate_limited"}.get(
        exc.status_code, "error")
    return _envelope(exc.status_code, code, exc.detail, request)


async def validation_exception_handler(request: Request,
                                       exc: RequestValidationError) -> JSONResponse:
    return _envelope(422, "validation_error", exc.errors(), request)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Never leak internals to the client; full detail goes to the logs only.
    log.exception("unhandled_error", extra={"path": request.url.path})
    return _envelope(500, "internal_error", "an unexpected error occurred", request)


def register(app) -> None:
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
