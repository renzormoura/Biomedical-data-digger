"""Aplicacao web: API JSON (FastAPI) + pagina servida por Jinja2.

Sem JavaScript, CSS ou fontes de terceiros em tempo de execucao: tudo vem de
`/static`. A Content-Security-Policy so permite recursos da propria origem.
"""

from __future__ import annotations

import hmac
import os
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger
from markupsafe import Markup
from pydantic import BaseModel, Field

import article_services
import markdown_lite
import pages
from account_store import (
    AccountStore,
    AccountStoreError,
    InvalidCredentialsFormat,
    get_account_store,
    validate_credentials,
)
from browse_api import register_browse_routes
from config import Settings
from discovery import DiscoveryService
from domain import (
    ArticleNotFoundError,
    AuthRequiredError,
    BackendUnavailableError,
    DiggerError,
    LimitReachedError,
    NotFoundError,
    RateLimitedError,
    SourceUnavailableError,
)
from library_store import LibraryStore
from presentation import UNVERIFIABLE_FALLBACK, verification_annex_md
from ratelimit import RateLimitExceeded, SlidingWindowLimiter, client_key
from sessions import SessionSigner
from usage import UsageLog
from workflow import AnalysisService, ArticleRepository, Filters, Reply

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_COOKIE = "bdd_session"
MAX_ARTICLE_ID = 2000
MAX_PREVIOUS_RESPONSE = 30_000

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; "
    "form-action 'self'; frame-ancestors 'none'"
)


# ---------------------------------------------------------------------------
# Modelos de requisicao (validacao na borda)
# ---------------------------------------------------------------------------
class FiltersIn(BaseModel):
    publico: str = Field("", max_length=80)
    tom: str = Field("", max_length=80)
    idioma: str = Field("", max_length=80)
    detalhe: str = Field("", max_length=80)
    foco: str = Field("", max_length=80)


class AnalyzeIn(BaseModel):
    page: str = Field(max_length=40)
    button: str = Field(max_length=80)
    article_id: str = Field(max_length=MAX_ARTICLE_ID)
    model: str = Field(max_length=80)
    filters: FiltersIn = Field(default_factory=lambda: FiltersIn(publico="", tom="", idioma="", detalhe="", foco=""))


class AuditIn(BaseModel):
    article_id: str = Field(max_length=MAX_ARTICLE_ID)
    model: str = Field(max_length=80)
    previous: str = Field(max_length=MAX_PREVIOUS_RESPONSE)
    page: str = Field("", max_length=40)


class CompareIn(BaseModel):
    article_a: str = Field(max_length=MAX_ARTICLE_ID)
    article_b: str = Field(max_length=MAX_ARTICLE_ID)
    analysis: str = Field(max_length=80)
    model: str = Field(max_length=80)
    clinical: bool = False
    page: str = Field("", max_length=40)


class ExtractIn(BaseModel):
    page: str = Field(max_length=40)
    button: str = Field(max_length=80)
    article_id: str = Field(max_length=MAX_ARTICLE_ID)


class CiteIn(BaseModel):
    article_id: str = Field(max_length=MAX_ARTICLE_ID)
    style: str = Field(max_length=20)


class SearchIn(BaseModel):
    query: str = Field(max_length=200)
    area: str = Field("Todas", max_length=60)
    limit: int = Field(5, ge=1, le=10)


class CredentialsIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)


# ---------------------------------------------------------------------------
# Fabrica da aplicacao
# ---------------------------------------------------------------------------
def create_app(
    service: AnalysisService,
    repository: ArticleRepository,
    settings: Settings,
    *,
    account_store_factory: Callable[[], AccountStore] = get_account_store,
    search_fn: Callable[..., list[dict]] = article_services.search_reliable_articles,
    usage_log: UsageLog | None = None,
    discovery: DiscoveryService | None = None,
    library: LibraryStore | None = None,
) -> FastAPI:
    app = FastAPI(title="Biomedical Data Digger", docs_url=None, redoc_url=None, openapi_url=None)
    signer = SessionSigner(settings.session_secret or SessionSigner.generate_secret())
    auth_limiter = SlidingWindowLimiter(settings.login_attempts_per_minute, window=60.0)
    templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
    static_dir = os.path.join(BASE_DIR, "static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    # Versao dos assets na URL: cache longo no navegador sem servir JS/CSS desatualizado.
    asset_version = format(
        int(max((os.path.getmtime(os.path.join(static_dir, name)) for name in os.listdir(static_dir)), default=0)),
        "x",
    )

    active_pages = pages.pages_for(settings.generative_clinical)
    page_by_key = {spec.key: spec for spec in active_pages}
    # Seguro: markdown_lite escapa todo texto antes de aplicar marcacao.
    help_html = {
        spec.key: Markup(markdown_lite.render(spec.help_markdown))  # noqa: S704
        for spec in active_pages
    }

    # -- infraestrutura ----------------------------------------------------
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

    @app.exception_handler(DiggerError)
    async def digger_error_handler(request: Request, error: DiggerError) -> JSONResponse:
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

    # -- identidade ----------------------------------------------------------
    def current_user(request: Request) -> str | None:
        return signer.verify(request.cookies.get(SESSION_COOKIE))

    def ip_of(request: Request) -> str:
        peer = request.client.host if request.client else None
        return client_key(dict(request.headers), peer, settings.trusted_proxy_hops)

    def identity(request: Request) -> str:
        user = current_user(request)
        return f"u:{user}" if user else f"ip:{ip_of(request)}"

    def throttle_auth(request: Request) -> None:
        try:
            auth_limiter.check(ip_of(request))
        except RateLimitExceeded as error:
            raise RateLimitedError(str(error)) from error

    def start_session(response: JSONResponse, email: str) -> None:
        response.set_cookie(
            SESSION_COOKIE, signer.issue(email), max_age=7 * 24 * 3600,
            httponly=True, samesite="lax", secure=settings.production, path="/",
        )

    def validated_model(model: str) -> str:
        if model not in pages.MODEL_CHOICES:
            raise DiggerError("Modelo de linguagem inválido.")
        return model

    # -- paginas ---------------------------------------------------------------
    @app.get("/")
    def index(request: Request):  # type: ignore[no-untyped-def]
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "pages": active_pages,
                "help_html": help_html,
                "models": pages.MODEL_CHOICES,
                "default_model": pages.DEFAULT_MODEL,
                "comparison_types": pages.COMPARISON_TYPES,
                "tones": pages.TONE_CHOICES,
                "languages": pages.LANGUAGE_CHOICES,
                "details": pages.DETAIL_CHOICES,
                "areas": list(article_services.AREA_KEYWORDS),
                "user": current_user(request),
                "asset_version": asset_version,
            },
        )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # -- autenticacao ----------------------------------------------------------
    @app.get("/api/auth/me")
    def me(request: Request) -> dict[str, Any]:
        return {"user": current_user(request)}

    def credentials(body: CredentialsIn) -> tuple[str, str]:
        try:
            return validate_credentials(body.email, body.password)
        except InvalidCredentialsFormat as error:
            raise DiggerError(str(error)) from error

    @app.post("/api/auth/register")
    def register(body: CredentialsIn, request: Request) -> JSONResponse:
        throttle_auth(request)
        email, password = credentials(body)
        try:
            created = account_store_factory().create_user(email, password)
        except AccountStoreError as error:
            raise DiggerError(str(error)) from error
        if not created:
            return JSONResponse({"error": "Este e-mail já está cadastrado."}, status_code=409)
        response = JSONResponse({"user": email})
        start_session(response, email)
        return response

    @app.post("/api/auth/login")
    def login(body: CredentialsIn, request: Request) -> JSONResponse:
        throttle_auth(request)
        try:
            email, password = validate_credentials(body.email, body.password)
            ok = account_store_factory().authenticate(email, password)
        except InvalidCredentialsFormat:
            ok = False
        except AccountStoreError as error:
            raise DiggerError(str(error)) from error
        if not ok:
            return JSONResponse({"error": "E-mail ou senha inválidos."}, status_code=401)
        response = JSONResponse({"user": email})
        start_session(response, email)
        return response

    @app.post("/api/auth/logout")
    def logout() -> JSONResponse:
        response = JSONResponse({"user": None})
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    # -- analises ----------------------------------------------------------------
    def result(markdown: str, article_id: str = "", reply: Reply | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"markdown": markdown, "html": markdown_lite.render(markdown)}
        if reply is not None:
            payload["meta"] = {
                "cached": reply.cached,
                "tokens": reply.tokens,
                "quota_remaining": reply.quota_remaining,
            }
        if article_id.strip():
            article = repository.peek(article_id)
            if article is not None:
                payload["title"] = article.title
                payload["article_id"] = article_id.strip()
        return payload

    @app.post("/api/analyze")
    def analyze(body: AnalyzeIn, request: Request) -> dict[str, Any]:
        spec = page_by_key.get(body.page)
        button = next((b for b in spec.buttons() if b.id == body.button), None) if spec else None
        if spec is None or button is None:
            raise ArticleNotFoundError("Análise desconhecida.")
        reply = service.analyze(
            body.article_id,
            validated_model(body.model),
            button.builder,
            button.heading,
            Filters(**body.filters.model_dump()),
            client_id=identity(request),
            clinical=spec.clinical,
            check_numbers=button.check_numbers,
            usage_key=f"{spec.key}/{button.id}",
            reasoning_effort=None if spec.clinical else button.reasoning_effort,
            requires=button.requires,
        )
        markdown = str(reply)
        if button.sources:
            try:
                markdown += verification_annex_md(button.sources)
            except Exception:
                logger.warning("Verificacao de fontes indisponivel para {}", button.id)
                markdown += UNVERIFIABLE_FALLBACK
        return result(markdown, body.article_id, reply)

    @app.post("/api/audit")
    def audit(body: AuditIn, request: Request) -> dict[str, Any]:
        reply = service.audit(
            body.article_id, validated_model(body.model), body.previous, client_id=identity(request),
            usage_key=f"{body.page}/audit" if body.page else "audit",
        )
        return result(str(reply), reply=reply)

    @app.post("/api/compare")
    def compare(body: CompareIn, request: Request) -> dict[str, Any]:
        if body.analysis not in pages.COMPARISON_TYPES:
            raise DiggerError("Tipo de comparação inválido.")
        reply = service.compare(
            body.article_a, body.article_b, body.analysis, validated_model(body.model),
            medical_context=body.clinical, client_id=identity(request),
            usage_key=f"{body.page}/compare" if body.page else "compare",
        )
        return result(str(reply), reply=reply)

    @app.get("/api/admin/usage")
    def admin_usage(request: Request) -> JSONResponse:
        """Relatorio de consumo de tokens. Desativado (404) sem ADMIN_TOKEN."""
        if not settings.admin_token or usage_log is None:
            return JSONResponse({"error": "Não encontrado."}, status_code=404)
        throttle_auth(request)
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(supplied.encode(), f"Bearer {settings.admin_token}".encode()):
            return JSONResponse({"error": "Não autorizado."}, status_code=401)
        return JSONResponse(usage_log.snapshot())

    @app.post("/api/extract")
    def extract(body: ExtractIn, request: Request) -> dict[str, Any]:
        """Extracao SEM IA: nenhum token e gasto e nenhum texto e gerado."""
        spec = page_by_key.get(body.page)
        button = next((b for b in spec.extract_buttons() if b.id == body.button), None) if spec else None
        if spec is None or button is None:
            raise ArticleNotFoundError("Extração desconhecida.")
        reply = service.extract(
            body.article_id, button.kind, label=button.label, client_id=identity(request), clinical=spec.clinical
        )
        return result(str(reply), body.article_id, reply)

    @app.post("/api/cite")
    def cite(body: CiteIn, request: Request) -> dict[str, Any]:
        return result(service.cite(body.article_id, body.style, client_id=identity(request)))

    @app.post("/api/search")
    def search(body: SearchIn, request: Request) -> dict[str, Any]:
        if not body.query.strip():
            raise DiggerError("Informe uma palavra-chave ou tema para buscar artigos relevantes.")
        if body.area not in article_services.AREA_KEYWORDS:
            raise DiggerError("Área de foco inválida.")
        try:
            items = search_fn(body.query, limit=body.limit, area=body.area)
        except RuntimeError as error:
            raise DiggerError(str(error)) from error
        if not items:
            raise ArticleNotFoundError(
                "Nenhum artigo foi encontrado para esta busca com o filtro selecionado. "
                "Tente outra palavra-chave ou área."
            )
        return {
            "results": [
                {
                    "title": item["title"],
                    "journal": item["journal"],
                    "year": str(item["year"]),
                    "pmid": item["pmid"],
                    "source": item["source"],
                    "url": item["url"] if str(item["url"]).startswith(("http://", "https://")) else "",
                    "doi": item.get("doi", ""),
                    "reliability": item["reliability"],
                    "score": item["reliability_score"],
                }
                for item in items
            ]
        }

    if discovery is not None and library is not None:
        register_browse_routes(app, discovery=discovery, library=library, current_user=current_user, identity=identity)

    return app
