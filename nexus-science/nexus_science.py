"""Ponto de entrada: monta as dependencias e sobe o servidor web."""

from __future__ import annotations

import os

import uvicorn
from fastapi import FastAPI

from account_consent import ConsentStore
from account_flags import AccountFlags
from account_store import get_account_store
from account_tokens import AccountTokens
from admin_service import AdminService
from alerts import AlertService, AlertStore
from arxiv_catalog import ArxivCatalog
from billing import BillingStore
from brasil import anvisa, conitec, rename
from catalog import Catalog
from config import Settings
from db import Database
from discovery import DiscoveryService
from doaj_catalog import DoajCatalog
from europepmc_catalog import EuropePmcCatalog
from feed import FeedService, FeedStore
from generation import GenerationPolicy
from library_store import get_library_store
from llm_service import get_router
from mailer import mailer_from_env
from notifications import NotificationService, NotificationStore
from openaire_catalog import OpenAireCatalog
from openalex_catalog import OpenAlexCatalog
from profiles import ProfileStore
from pubmed_catalog import PubMedCatalog
from quota import QuotaManager
from ratelimit import SlidingWindowLimiter
from reports import ReportStore
from usage import UsageLog
from web import create_app as create_web_app
from workflow import AnalysisService, ArticleRepository


def load_brazil_bases() -> tuple[anvisa.Instantaneo, conitec.Instantaneo, rename.Instantaneo] | None:
    """Instantaneos da ANVISA, da Conitec e da Rename; None se algum nao puder ser lido (o vigia regulatorio fica de fora)."""
    try:
        return anvisa.carregar(), conitec.carregar(), rename.carregar()
    except (OSError, ValueError, KeyError):
        return None


def create_app() -> FastAPI:
    settings = Settings.from_env()
    repository = ArticleRepository()
    usage_log = UsageLog()
    service = AnalysisService(
        repository=repository,
        generator=get_router(),
        limiter=SlidingWindowLimiter(settings.llm_calls_per_minute, window=60.0),
        usage_log=usage_log,
        quota=QuotaManager(settings.daily_token_budget_guest, settings.daily_token_budget_user),
        policy=GenerationPolicy(temperature=settings.llm_temperature),
    )
    catalogs: list[Catalog] = [EuropePmcCatalog()]
    if settings.openalex_api_key:  # OpenAlex so entra com chave propria (sem ela o orcamento e minusculo)
        catalogs.append(OpenAlexCatalog(settings.openalex_api_key, settings.openalex_mailto))
    catalogs += [PubMedCatalog(settings.ncbi_api_key), ArxivCatalog(), DoajCatalog(), OpenAireCatalog()]
    discovery = DiscoveryService(catalogs, SlidingWindowLimiter(settings.discovery_calls_per_minute, window=60.0))
    alert_store = AlertStore()
    alert_store.initialize()
    report_store = ReportStore()
    report_store.initialize()
    profile_store = ProfileStore()
    profile_store.initialize()
    alerts = AlertService(
        alert_store,
        lambda query, user: discovery.search(query, source=discovery.search_default, client_id=f"alertas:{user}").works,
    )
    library = get_library_store()
    feed_store = FeedStore()
    feed_store.initialize()
    notification_store = NotificationStore()
    notification_store.initialize()
    notifications = NotificationService(
        notification_store,
        fetch_work=lambda ref: discovery.work(ref, client_id="vigia-retratacoes"),
        library=library, reports=report_store, bases=load_brazil_bases,
    )
    get_account_store()  # cria a tabela de contas na subida: sem banco, o servico falha aqui e nao no primeiro login
    account_tokens = AccountTokens()
    account_tokens.initialize()
    consent = ConsentStore()
    consent.initialize()
    billing = BillingStore()
    billing.initialize()
    flags = AccountFlags()
    flags.initialize()
    account_tokens_db = Database()
    admin = AdminService(account_tokens_db, billing, account_tokens, consent, flags)
    return create_web_app(
        service, repository, settings, usage_log=usage_log, discovery=discovery, library=library, alerts=alerts,
        reports=report_store, profiles=profile_store, notifications=notifications, feed=FeedService(feed_store),
        account_tokens=account_tokens, mailer=mailer_from_env(settings.production), consent=consent, billing=billing, flags=flags, admin=admin,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    # Render exige bind em todas as interfaces.
    uvicorn.run(create_app(), host="0.0.0.0", port=port, log_level="info")  # noqa: S104
