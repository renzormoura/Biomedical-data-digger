"""Rotas: Feed de novidades academicas."""

from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import quote

from fastapi import FastAPI, Query, Request

from feed_sources import SOURCES as FEED_SOURCES
from feed_sources import TIERS as FEED_TIERS
from interests import area_label
from routes.context import ApiContext


def register_feed_routes(app: FastAPI, ctx: ApiContext) -> None:
    current_user = ctx.current_user
    alerts = ctx.alerts
    feed = ctx.feed

    # -- feed de novidades academicas --------------------------------------------------
    if feed is not None:
        feed_service = feed

        @app.get("/api/feed")
        def get_feed(
            request: Request,
            mode: Annotated[str, Query(pattern="^(voce|tudo)$")] = "voce",
            kind: Annotated[str, Query(pattern="^(todos|artigos|noticias)$")] = "todos",
            area: Annotated[str, Query(max_length=30)] = "",
            lang: Annotated[str, Query(max_length=5)] = "",
            page: Annotated[int, Query(ge=1, le=50)] = 1,
        ) -> dict[str, Any]:
            """Novidades de fontes academicas curadas (noticias e revistas); em "voce", so o que cita os interesses da conta."""
            user = current_user(request)
            prefs = alerts.store.preferences(user)[0] if user and alerts is not None else None
            articles: list[dict[str, Any]] = []
            if user and alerts is not None:  # os artigos novos dos interesses entram no feed, abrindo a pagina do artigo aqui dentro
                articles = [
                    {
                        "id": a.id, "kind": "artigo", "title": a.work.title, "snippet": " · ".join(p for p in [a.work.author_line, a.work.journal, str(a.work.year or "")] if p)[:300],
                        "url": f"#/artigo?ref={quote(a.work.ref, safe='')}", "internal": True, "publishedAt": a.created_at, "dateKnown": True, "areas": [],
                        "matched": [a.topic], "source": {"id": "interesses", "name": "Seus interesses", "tier": "interesses", "tierLabel": "Artigo novo",
                                                         "language": a.work.language, "site": ""},
                    }
                    for a in alerts.store.alerts(user, limit=40)
                ]
            refreshing = feed_service.refresh_in_background()
            result = feed_service.page(prefs=prefs, mode=mode, kind=kind, area=area, language=lang, page=page, article_items=articles if mode == "voce" else [])
            return {
                "items": result.items, "total": result.total, "hasMore": result.has_more, "personalized": result.personalized,
                "hasInterests": bool(prefs and not prefs.empty), "updatedAt": result.updated_at, "refreshing": refreshing or not result.updated_at,
                "page": page,
            }

        @app.get("/api/feed/sources")
        def get_feed_sources() -> dict[str, Any]:
            """Fontes do feed, com o tipo de cada uma e quando foram atualizadas pela ultima vez (transparencia)."""
            states = feed_service.store.states()
            return {
                "tiers": [{"key": key, "label": label, "description": description} for key, (label, description) in FEED_TIERS.items()],
                "sources": [
                    {
                        "id": s.id, "name": s.name, "site": s.site, "language": s.language, "tier": s.tier, "tierLabel": FEED_TIERS[s.tier][0],
                        "areas": [area_label(a) for a in s.areas] or ["Qualquer área"],
                        "lastOk": states[s.id].last_ok if s.id in states else "", "failing": bool(s.id in states and states[s.id].error),
                    }
                    for s in FEED_SOURCES
                ],
            }
