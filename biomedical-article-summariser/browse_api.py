"""Rotas JSON do navegador de artigos: descoberta, biblioteca, listas e exportacao.

Registradas por `web.create_app`. Descoberta e leitura publica nao exigem conta; salvar,
etiquetar, listar e exportar exigem sessao. Nada aqui chama IA nem gasta token.

O codigo das rotas vive em `routes/` (um modulo por dominio); este modulo so monta o contexto de dependencias
e registra cada grupo, na mesma ordem de sempre.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, Request

from alerts import AlertService
from billing import BillingStore
from config import Settings
from discovery import DiscoveryService
from feed import FeedService
from library_store import LibraryStore
from mailer import Mailer
from notifications import NotificationService
from profiles import ProfileStore
from reports import ReportStore
from routes.analyses import register_analyses_routes
from routes.billing import register_billing_routes
from routes.context import ApiContext
from routes.discover import register_discover_routes
from routes.feed import register_feed_routes
from routes.library import register_library_routes
from routes.profile import register_profile_routes
from routes.reports import register_reports_routes
from routes.watch import register_watch_routes


def register_browse_routes(
    app: FastAPI,
    *,
    discovery: DiscoveryService,
    library: LibraryStore,
    current_user: Callable[[Request], str | None],
    identity: Callable[[Request], str],
    alerts: AlertService | None = None,
    cron_token: str = "",
    reports: ReportStore | None = None,
    profiles: ProfileStore | None = None,
    notifications: NotificationService | None = None,
    feed: FeedService | None = None,
    billing: BillingStore | None = None,
    settings: Settings | None = None,
    admin_token: str = "",
    mailer: Mailer | None = None,
    account_exists: Callable[[str], bool] | None = None,
) -> None:
    ctx = ApiContext(
        discovery=discovery, library=library, current_user=current_user, identity=identity, alerts=alerts,
        cron_token=cron_token, reports=reports, profiles=profiles, notifications=notifications, feed=feed,
        billing=billing, settings=settings, admin_token=admin_token, mailer=mailer,
        account_exists=account_exists or (lambda email: False),
    )
    register_discover_routes(app, ctx)
    register_analyses_routes(app, ctx)
    register_profile_routes(app, ctx)
    register_feed_routes(app, ctx)
    register_reports_routes(app, ctx)
    register_watch_routes(app, ctx)
    register_library_routes(app, ctx)
    register_billing_routes(app, ctx)
