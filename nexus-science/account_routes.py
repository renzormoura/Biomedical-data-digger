"""Rotas da conta: resumo do perfil, troca de senha, copia dos dados e exclusao (LGPD).

Todas exigem sessao. Troca de senha e exclusao pedem a senha atual e passam pelo mesmo limite de tentativas do login.
A exclusao apaga a conta e tudo o que ela guardou (biblioteca, listas, analises, relatorios, interesses, avisos e perfil).
Observacao: a sessao e um cookie assinado sem estado no servidor; trocar a senha NAO encerra a sessao de outros aparelhos.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from account_consent import ConsentStore
from account_flags import AccountFlags
from account_store import AccountStore, AccountStoreError, InvalidCredentialsFormat, validate_credentials
from account_tokens import AccountTokens
from alerts import AlertStore
from billing import BillingStore
from domain import AuthRequiredError, NexusError
from library_store import LibraryStore
from notifications import NotificationStore
from profiles import ProfileError, ProfileStore
from reports import ReportStore
from timeutil import utcnow_iso


class NameIn(BaseModel):
    name: str = Field(max_length=120)


class PasswordIn(BaseModel):
    current: str = Field(max_length=200)
    new: str = Field(max_length=200)


class DeleteIn(BaseModel):
    password: str = Field(max_length=200)


def _terms(consent: ConsentStore | None, user: str) -> dict[str, str] | None:
    accepted = consent.get(user) if consent is not None else None
    return {"version": accepted[0], "acceptedAt": accepted[1]} if accepted else None


def make_account_purger(
    *, account_store_factory: Callable[[], AccountStore], library: LibraryStore, reports: ReportStore | None, alerts: AlertStore | None,
    profiles: ProfileStore | None, notifications: NotificationStore | None, tokens: AccountTokens | None,
    consent: ConsentStore | None, billing: BillingStore | None, flags: AccountFlags | None,
) -> Callable[[str], None]:
    """Apaga a conta e tudo o que ela guardou, em todos os armazens (usada pela propria pessoa e pelo administrador)."""

    def purge(user: str) -> None:
        library.delete_user_data(user)
        if reports is not None:
            reports.delete_user_data(user)
        if alerts is not None:
            alerts.delete_user_data(user)
        if profiles is not None:
            profiles.delete(user)
        if notifications is not None:
            notifications.delete_user_data(user)
        if tokens is not None:
            tokens.delete_user_data(user)
        if consent is not None:
            consent.delete_user_data(user)
        if billing is not None:
            billing.delete_user_data(user)  # os pagamentos confirmados ficam (registro fiscal)
        if flags is not None:
            flags.delete_user_data(user)
        try:
            account_store_factory().delete_user(user)
        except AccountStoreError as error:
            raise NexusError(str(error)) from error

    return purge


def register_account_routes(
    app: FastAPI,
    *,
    account_store_factory: Callable[[], AccountStore],
    current_user: Callable[[Request], str | None],
    throttle_auth: Callable[[Request], None],
    on_deleted: Callable[[JSONResponse, str], None],
    library: LibraryStore,
    reports: ReportStore | None,
    alerts: AlertStore | None,
    profiles: ProfileStore | None,
    notifications: NotificationStore | None = None,
    tokens: AccountTokens | None = None,
    mail_enabled: bool = False,
    consent: ConsentStore | None = None,
    billing: BillingStore | None = None,
    purge: Callable[[str], None] | None = None,
) -> None:
    def require_user(request: Request) -> str:
        user = current_user(request)
        if user is None:
            raise AuthRequiredError("Entre na sua conta para ver o perfil.")
        return user

    def purge_account(user: str) -> None:
        if purge is not None:
            purge(user)
            return
        make_account_purger(
            account_store_factory=account_store_factory, library=library, reports=reports, alerts=alerts, profiles=profiles,
            notifications=notifications, tokens=tokens, consent=consent, billing=billing, flags=None,
        )(user)

    def confirm_password(user: str, password: str) -> None:
        try:
            ok = account_store_factory().authenticate(user, password.strip())
        except AccountStoreError as error:
            raise NexusError(str(error)) from error
        if not ok:
            raise NexusError("Senha incorreta.")

    @app.get("/api/account")
    def account_summary(request: Request) -> dict[str, Any]:
        user = require_user(request)
        try:
            created = account_store_factory().created_at(user)
        except AccountStoreError as error:
            raise NexusError(str(error)) from error
        counts = {
            "library": len(library.items(user)), "lists": len(library.lists(user)), "analyses": len(library.analyses(user)),
            "reports": len(reports.summaries(user)) if reports else 0,
        }
        interests: dict[str, Any] = {"topics": 0, "terms": 0, "languages": 0, "unread": 0, "lastChecked": None}
        if alerts is not None:
            prefs, checked = alerts.preferences(user)
            interests = {
                "topics": len(prefs.selected()), "terms": len(prefs.terms), "languages": len(prefs.languages),
                "unread": alerts.unread(user), "lastChecked": checked.isoformat(timespec="seconds") if checked else None,
            }
        profile = profiles.get(user) if profiles else None
        return {
            "email": user, "name": profiles.name(user) if profiles else "", "createdAt": created, "counts": counts, "interests": interests,
            "emailVerified": tokens.is_verified(user) if tokens is not None else None, "emailEnabled": mail_enabled,
            "profile": {"profile": profile.key, "healthPack": profile.health_pack, "configured": profile.configured} if profile else None,
        }

    @app.put("/api/account/name")
    def set_name(body: NameIn, request: Request) -> dict[str, str]:
        user = require_user(request)
        if profiles is None:
            raise NexusError("O perfil não está disponível neste servidor.")
        try:
            return {"name": profiles.set_name(user, body.name)}
        except ProfileError as error:
            raise NexusError(str(error)) from error

    @app.post("/api/account/password")
    def change_password(body: PasswordIn, request: Request) -> dict[str, bool]:
        user = require_user(request)
        throttle_auth(request)
        confirm_password(user, body.current)
        try:
            _, new_password = validate_credentials(user, body.new)
        except InvalidCredentialsFormat as error:
            raise NexusError(str(error)) from error
        if new_password == body.current.strip():
            raise NexusError("A nova senha precisa ser diferente da atual.")
        try:
            account_store_factory().change_password(user, new_password)
        except AccountStoreError as error:
            raise NexusError(str(error)) from error
        return {"ok": True}

    @app.get("/api/account/export")
    def export_data(request: Request) -> Response:
        """Copia de todos os dados da conta em JSON (sem a senha), para portabilidade."""
        user = require_user(request)
        try:
            created = account_store_factory().created_at(user)
        except AccountStoreError as error:
            raise NexusError(str(error)) from error
        profile = profiles.get(user) if profiles else None
        payload: dict[str, Any] = {
            "exportedAt": utcnow_iso(),
            "account": {"email": user, "name": profiles.name(user) if profiles else "", "createdAt": created, "emailVerified": tokens.is_verified(user) if tokens is not None else None,
                        "terms": _terms(consent, user)},
            "profile": {"profile": profile.key, "healthPack": profile.health_pack} if profile else None,
            "library": [{**item.work.to_dict(), "tags": list(item.tags), "savedAt": item.saved_at} for item in library.items(user)],
            "lists": [
                {"name": item.name, "createdAt": item.created_at, "shared": item.share_token is not None, "works": [w.to_dict() for w in item.works]}
                for item in library.lists(user)
            ],
            "analyses": [
                {"article": item.title, "ref": item.ref, "page": item.page, "label": item.label, "markdown": item.markdown, "createdAt": item.created_at}
                for item in library.analyses(user)
            ],
        }
        if reports is not None:
            payload["reports"] = []
            for summary in reports.summaries(user):
                report = reports.get(user, summary.id)
                payload["reports"].append({
                    "title": report.title, "question": report.question, "methodNote": report.method_note, "listName": report.list_name,
                    "createdAt": report.created_at, "updatedAt": report.updated_at, "version": report.version, "substances": list(report.substances),
                    "history": [{"kind": e.kind, "text": e.text, "createdAt": e.created_at} for e in report.log],
                    "studies": [{**item.work.to_dict(), "included": item.included, "note": item.note} for item in report.items],
                })
        if alerts is not None:
            prefs, _checked = alerts.preferences(user)
            payload["interests"] = prefs.to_dict()
            payload["alerts"] = [
                {"topic": a.topic, "createdAt": a.created_at, "read": a.read, "work": a.work.to_dict()} for a in alerts.alerts(user, limit=200)
            ]
        if billing is not None:
            current = billing.subscription(user)
            payload["subscription"] = {"plan": current.plan, "expiresAt": current.expires_at.isoformat(timespec="seconds")} if current else None
            payload["payments"] = [
                {"plan": r.plan, "months": r.months, "amountCents": r.amount_cents, "status": r.status, "reference": r.reference,
                 "createdAt": r.created_at, "confirmedAt": r.confirmed_at}
                for r in billing.requests(user)
            ]
        if notifications is not None:
            payload["notifications"] = [
                {"kind": n.kind, "title": n.title, "body": n.body, "link": n.link, "createdAt": n.created_at, "read": n.read}
                for n in notifications.notifications(user, limit=200)
            ]
            payload["notificationPrefs"] = notifications.prefs(user)
        return Response(
            json.dumps(payload, ensure_ascii=False, indent=2), media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="meus-dados.json"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @app.delete("/api/account")
    def delete_account(body: DeleteIn, request: Request) -> JSONResponse:
        """Exclui a conta e todos os dados dela. Pede a senha e nao tem volta."""
        user = require_user(request)
        throttle_auth(request)
        confirm_password(user, body.password)
        purge_account(user)
        response = JSONResponse({"deleted": True})
        on_deleted(response, user)
        return response
