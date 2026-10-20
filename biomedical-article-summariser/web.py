"""Aplicacao web: API JSON (FastAPI) + pagina servida por Jinja2.

Sem JavaScript, CSS ou fontes de terceiros em tempo de execucao: tudo vem de
`/static`. A Content-Security-Policy so permite recursos da propria origem.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from pydantic import BaseModel, ConfigDict, Field

import article_services
import legal
import markdown_lite
import pages
from account_consent import ConsentStore
from account_flags import AccountFlags
from account_routes import make_account_purger, register_account_routes
from account_store import (
    AccountStore,
    AccountStoreError,
    InvalidCredentialsFormat,
    get_account_store,
    validate_credentials,
)
from account_tokens import AccountTokens
from admin_service import AdminService
from alerts import AlertService
from billing import BillingStore
from browse_api import register_browse_routes
from cache import TTLCache
from config import Settings
from discovery import DiscoveryService
from domain import (
    DiggerError,
    RateLimitedError,
)
from feed import FeedService
from library_store import LibraryStore
from mailer import Mailer
from notifications import NotificationService
from profiles import DEFAULT as DEFAULT_PROFILE
from profiles import ProfileStore
from ratelimit import RateLimitExceeded, SlidingWindowLimiter, client_key
from reports import ReportStore
from routes.hardening import install_http_hardening
from routes.lab import LabContext, register_lab_routes
from routes.legal import register_legal_routes
from routes.recovery import RecoveryContext, register_recovery_routes
from sessions import SessionSigner
from usage import UsageLog
from workflow import AnalysisService, ArticleRepository

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_COOKIE = "bdd_session"

# ---------------------------------------------------------------------------
# Modelos de requisicao (validacao na borda)
# ---------------------------------------------------------------------------
class CredentialsIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    accept_terms: bool = Field(False, alias="acceptTerms")
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
    alerts: AlertService | None = None,
    reports: ReportStore | None = None,
    profiles: ProfileStore | None = None,
    notifications: NotificationService | None = None,
    feed: FeedService | None = None,
    account_tokens: AccountTokens | None = None,
    mailer: Mailer | None = None,
    consent: ConsentStore | None = None,
    billing: BillingStore | None = None,
    flags: AccountFlags | None = None,
    admin: AdminService | None = None,
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

    install_http_hardening(app, settings)

    # -- identidade ----------------------------------------------------------
    # a sessao e um cookie assinado, sem estado: conferimos (com cache curto) se a conta ainda existe, para que
    # uma conta excluida nao continue "logada" em outros aparelhos
    exists_cache: TTLCache[bool] = TTLCache(1024, 30.0)

    def current_user(request: Request) -> str | None:
        user = signer.verify(request.cookies.get(SESSION_COOKIE))
        if user is None:
            return None
        known = exists_cache.get(user)
        if known is None:
            try:
                known = account_store_factory().exists(user) and not (flags is not None and flags.is_suspended(user))
            except AccountStoreError:
                known = True  # banco de contas fora do ar: nao derruba a sessao
            exists_cache.set(user, known)
        return user if known else None

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

    def end_account(response: JSONResponse, email: str) -> None:
        exists_cache.set(email, False)
        response.delete_cookie(SESSION_COOKIE, path="/")

    def start_session(response: JSONResponse, email: str) -> None:
        exists_cache.set(email, True)
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
        """Navegador de artigos: busca, leitura, biblioteca e listas."""
        user = current_user(request)
        profile = profiles.get(user) if profiles is not None else DEFAULT_PROFILE
        return templates.TemplateResponse(
            request, "browse.html",
            {"user": user, "asset_version": asset_version, "profile": profile.key or "", "health_pack": "1" if profile.health_pack else "0"},
        )

    @app.get("/ia")
    def ia_lab(request: Request):  # type: ignore[no-untyped-def]
        """Laboratorio de IA: resumos e analises opcionais (extracao sem IA e analises geradas)."""
        return templates.TemplateResponse(
            request,
            "ia.html",
            {
                "pages": active_pages,
                "page_groups": pages.grouped(active_pages),
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

    register_legal_routes(app, settings)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # -- autenticacao ----------------------------------------------------------
    recovery: RecoveryContext | None = None
    if account_tokens is not None:
        recovery = RecoveryContext(
            account_store_factory=account_store_factory, tokens=account_tokens, mailer=mailer, base_url=settings.app_base_url,
            throttle_auth=throttle_auth, current_user=current_user,
        )
        register_recovery_routes(app, recovery)

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
        if settings.require_terms and not body.accept_terms:
            raise DiggerError("Aceite os Termos de Uso e a Política de Privacidade para criar a conta.")
        try:
            created = account_store_factory().create_user(email, password)
        except AccountStoreError as error:
            raise DiggerError(str(error)) from error
        if not created:
            return JSONResponse({"error": "Este e-mail já está cadastrado."}, status_code=409)
        if consent is not None and body.accept_terms:
            consent.record(email, legal.VERSION)
        if recovery is not None:
            recovery.send_verification(email)
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
        if flags is not None and flags.is_suspended(email):
            return JSONResponse({"error": "Esta conta está suspensa. Fale com o suporte."}, status_code=403)
        response = JSONResponse({"user": email})
        start_session(response, email)
        return response

    @app.post("/api/auth/logout")
    def logout() -> JSONResponse:
        response = JSONResponse({"user": None})
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    register_lab_routes(app, LabContext(
        service=service, repository=repository, settings=settings, usage_log=usage_log, page_by_key=page_by_key,
        identity=identity, validated_model=validated_model, throttle_auth=throttle_auth, search_fn=search_fn,
    ))

    purge: Callable[[str], None] | None = None
    if library is not None:
        purge = make_account_purger(
            account_store_factory=account_store_factory, library=library, reports=reports, alerts=alerts.store if alerts is not None else None,
            profiles=profiles, notifications=notifications.store if notifications is not None else None, tokens=account_tokens,
            consent=consent, billing=billing, flags=flags,
        )
        register_account_routes(
            app, account_store_factory=account_store_factory, current_user=current_user, throttle_auth=throttle_auth, on_deleted=end_account,
            library=library, reports=reports, alerts=alerts.store if alerts is not None else None, profiles=profiles,
            notifications=notifications.store if notifications is not None else None,
            tokens=account_tokens, mail_enabled=recovery is not None and recovery.enabled, consent=consent,
            billing=billing, purge=purge,
        )

    if discovery is not None and library is not None:
        register_browse_routes(
            app, discovery=discovery, library=library, current_user=current_user, identity=identity, alerts=alerts,
            cron_token=settings.alerts_cron_token, reports=reports, profiles=profiles, notifications=notifications, feed=feed,
            billing=billing, settings=settings, admin_token=settings.admin_token, mailer=mailer,
            account_exists=lambda email: account_store_factory().exists(email),
            admin=admin, flags=flags, purge_account=purge,
            email_verified=(lambda email: account_tokens.is_verified(email)) if account_tokens is not None else None,
            mark_verified=account_tokens.mark_verified if account_tokens is not None else None,
            send_reset=recovery.send_reset if recovery is not None else None,
            session_changed=lambda email, allowed: exists_cache.set(email, allowed),
            usage_snapshot=usage_log.snapshot if usage_log is not None else None,
        )

    return app
