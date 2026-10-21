"""Rotas: Interesses, alertas, notificacoes e a rotina agendada."""

from __future__ import annotations

import hmac
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from alerts import Alert, CheckResult
from domain import NotFoundError, RateLimitedError
from interests import catalogo, validar
from notifications import KINDS, Notification
from ratelimit import RateLimitExceeded, SlidingWindowLimiter
from routes.context import ApiContext
from routes.payloads import (
    work_card,
)
from routes.schemas import (
    CheckIn,
    InterestsIn,
    NotificationPrefsIn,
    ReadIn,
)


def register_watch_routes(app: FastAPI, ctx: ApiContext) -> None:
    identity = ctx.identity
    alerts = ctx.alerts
    cron_token = ctx.cron_token
    notifications = ctx.notifications
    feed = ctx.feed
    require_user = ctx.require_user

    # -- interesses e alertas -------------------------------------------------------
    if alerts is not None:
        alert_service = alerts

        watcher = notifications

        def alert_payload(item: Alert) -> dict[str, Any]:
            return {
                "id": item.id, "kind": "novo-artigo", "priority": KINDS["novo-artigo"][0], "title": item.work.title, "body": "",
                "href": f"#/artigo?ref={quote(item.work.ref, safe='')}", "topic": item.topic, "createdAt": item.created_at, "read": item.read,
                "work": work_card(item.work),
            }

        def notification_payload(item: Notification) -> dict[str, Any]:
            return {
                "id": item.id, "kind": item.kind, "priority": item.priority, "title": item.title, "body": item.body, "href": item.link,
                "topic": KINDS[item.kind][1] if item.kind in KINDS else "", "createdAt": item.created_at, "read": item.read, "work": None,
            }

        def box(user: str) -> dict[str, Any]:
            """Caixa unica do sininho: artigos novos dos interesses mais os avisos de retratacao, regulatorio e relatorios."""
            items = [alert_payload(a) for a in alert_service.store.alerts(user)]
            unread = alert_service.store.unread(user)
            if watcher is not None:
                items += [notification_payload(n) for n in watcher.store.notifications(user)]
                unread += watcher.store.unread(user)
            items.sort(key=lambda entry: entry["createdAt"], reverse=True)
            items.sort(key=lambda entry: (entry["read"], -entry["priority"]))  # nao lidos primeiro, os mais importantes no topo
            return {"unread": unread, "alerts": items[:100]}

        @app.get("/api/interests/options")
        def interest_options() -> dict[str, Any]:
            return catalogo()

        @app.get("/api/interests")
        def get_interests(request: Request) -> dict[str, Any]:
            prefs, checked = alert_service.store.preferences(require_user(request))
            return {**prefs.to_dict(), "lastChecked": checked.isoformat(timespec="seconds") if checked else None}

        @app.put("/api/interests")
        def put_interests(body: InterestsIn, request: Request) -> dict[str, Any]:
            user = require_user(request)
            prefs = validar([t.model_dump() for t in body.topics], body.languages, body.terms)
            alert_service.store.set_preferences(user, prefs)
            return prefs.to_dict()

        @app.get("/api/alerts")
        def get_alerts(request: Request) -> dict[str, Any]:
            return box(require_user(request))

        @app.post("/api/alerts/check")
        def check_alerts(body: CheckIn, request: Request) -> dict[str, Any]:
            user = require_user(request)
            enabled = watcher.store.prefs(user) if watcher is not None else dict.fromkeys(KINDS, True)
            result = alert_service.check(user, force=body.force) if enabled["novo-artigo"] else CheckResult(False, reason="desativado")
            watched = watcher.run(user, force=body.force) if watcher is not None else None
            return {
                "ran": result.ran or bool(watched and watched.ran), "new": result.new + (watched.total if watched else 0),
                "reason": result.reason, "baseline": result.baseline, "notes": list(result.notes),
                "notified": watched.created if watched else {}, **box(user),
            }

        cron_limiter = SlidingWindowLimiter(10, window=60.0)

        @app.post("/api/internal/alerts/run")
        def run_scheduled_alerts(request: Request) -> JSONResponse:
            """Verificacao agendada para todas as contas. Desativada (404) sem ALERTS_CRON_TOKEN."""
            if not cron_token:
                return JSONResponse({"error": "Não encontrado."}, status_code=404)
            try:
                cron_limiter.check(identity(request))
            except RateLimitExceeded as error:
                raise RateLimitedError(str(error)) from error
            supplied = request.headers.get("authorization", "")
            if not hmac.compare_digest(supplied.encode(), f"Bearer {cron_token}".encode()):
                return JSONResponse({"error": "Não autorizado."}, status_code=401)
            summary: dict[str, Any] = dict(alert_service.check_all())
            if watcher is not None:
                summary["watch"] = watcher.run_all()
            if feed is not None:
                summary["feed"] = feed.refresh()
            return JSONResponse(summary)

        @app.post("/api/alerts/read")
        def read_alerts(body: ReadIn, request: Request) -> dict[str, Any]:
            user = require_user(request)
            if body.id is None:
                alert_service.store.mark_read(user)
                if watcher is not None:
                    watcher.store.mark_read(user)
            else:
                try:
                    alert_service.store.mark_read(user, body.id)
                except NotFoundError:
                    if watcher is None or not watcher.store.mark_read(user, body.id):
                        raise
            return box(user)

        @app.delete("/api/alerts")
        def dismiss_alert(request: Request, id: Annotated[str, Query(min_length=1, max_length=64)]) -> dict[str, Any]:  # noqa: A002
            user = require_user(request)
            alert_service.store.dismiss(user, id)
            if watcher is not None:
                watcher.store.dismiss(user, id)
            return box(user)

        @app.get("/api/notifications/prefs")
        def get_notification_prefs(request: Request) -> dict[str, Any]:
            """Tipos de aviso do sininho, com o que cada um faz e se esta ligado (tudo ligado por padrao)."""
            user = require_user(request)
            enabled = watcher.store.prefs(user) if watcher is not None else dict.fromkeys(KINDS, True)
            return {
                "channel": "sininho",
                "kinds": [{"key": key, "priority": priority, "label": label, "description": description, "enabled": enabled[key]}
                          for key, (priority, label, description) in KINDS.items()],
            }

        @app.put("/api/notifications/prefs")
        def put_notification_prefs(body: NotificationPrefsIn, request: Request) -> dict[str, Any]:
            user = require_user(request)
            if watcher is not None:
                watcher.store.set_prefs(user, body.kinds)
            return get_notification_prefs(request)
