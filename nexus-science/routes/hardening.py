"""Endurecimento HTTP: cabecalhos de seguranca, checagem de origem e tratamento padrao de erros."""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger

from config import Settings
from domain import (
    AuthRequiredError,
    BackendUnavailableError,
    LimitReachedError,
    NexusError,
    NotFoundError,
    RateLimitedError,
    SourceUnavailableError,
)

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; "
    "form-action 'self'; frame-ancestors 'none'"
)



def install_http_hardening(app: FastAPI, settings: Settings) -> None:
    @app.middleware("http")
    async def security_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin and urlparse(origin).netloc != request.headers.get("host", ""):
                return JSONResponse({"error": "Origem não permitida."}, status_code=403)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if settings.production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=3600"
        return response

    @app.exception_handler(NexusError)
    async def nexus_error_handler(request: Request, error: NexusError) -> JSONResponse:
        status = 400
        if isinstance(error, RateLimitedError):
            status = 429
        elif isinstance(error, AuthRequiredError):
            status = 401
        elif isinstance(error, NotFoundError):
            status = 404
        elif isinstance(error, LimitReachedError):
            status = 409
        elif isinstance(error, (BackendUnavailableError, SourceUnavailableError)):
            status = 503
        return JSONResponse({"error": error.user_message}, status_code=status)

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, error: Exception) -> JSONResponse:
        logger.exception("Erro inesperado em {} {}", request.method, request.url.path)
        return JSONResponse({"error": "Erro interno. Tente novamente em instantes."}, status_code=500)
