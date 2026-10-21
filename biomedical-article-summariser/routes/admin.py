"""Rotas do painel de administracao: visao geral, usuarios e seus planos, pagamentos, suspensao, exclusao e estado do sistema.

Quem e administrador: (a) a pessoa logada cujo e-mail esta em `ADMIN_EMAILS` (em producao, com o e-mail **confirmado**), ou
(b) quem envia `Authorization: Bearer ADMIN_TOKEN` (acesso por script ou emergencia). Sem nenhum dos dois configurados, tudo
aqui responde 404. Toda acao de escrita vai para o log com quem fez, o que fez e em quem.
"""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field

import plans
from billing import CONFIRMED, PENDING
from domain import DiggerError, NotFoundError, RateLimitedError
from mailer import EmailMessage, MailError
from ratelimit import RateLimitExceeded
from routes.context import ApiContext


class AdminUnauthorizedError(Exception):
    """Nao e administrador (vira 401 sem detalhes)."""


class NoteIn(BaseModel):
    note: str = Field("", max_length=300)


class ReasonIn(BaseModel):
    reason: str = Field("", max_length=300)


class GrantIn(BaseModel):
    email: str = Field(max_length=320)
    plan: str = Field(max_length=20)
    days: int = Field(ge=1, le=3660)


class EmailIn(BaseModel):
    email: str = Field(max_length=320)


class ConfirmDeleteIn(BaseModel):
    confirm: str = Field(max_length=320)


def register_admin_routes(app: FastAPI, ctx: ApiContext) -> None:
    billing, settings, admin = ctx.billing, ctx.settings, ctx.admin
    if billing is None or settings is None or admin is None:
        return
    catalog = plans.catalog(settings)

    def actor_of(request: Request) -> str | None:
        """Quem esta agindo como administrador: "token", o e-mail da pessoa logada, ou `None`."""
        supplied = request.headers.get("authorization", "")
        if ctx.admin_token and hmac.compare_digest(supplied.encode(), f"Bearer {ctx.admin_token}".encode()):
            return "token"
        user = ctx.current_user(request)
        if user and user in settings.admin_emails and (not settings.production or ctx.email_verified(user)):
            return user
        return None

    def require_admin(request: Request) -> str:
        if not ctx.admin_token and not settings.admin_emails:
            raise NotFoundError("Não encontrado.")
        try:
            ctx.admin_limiter.check(ctx.identity(request))
        except RateLimitExceeded as error:
            raise RateLimitedError(str(error)) from error
        actor = actor_of(request)
        if actor is None:
            raise AdminUnauthorizedError
        return actor

    @app.exception_handler(AdminUnauthorizedError)
    async def unauthorized(request: Request, error: AdminUnauthorizedError) -> JSONResponse:
        return JSONResponse({"error": "Não autorizado."}, status_code=401)

    def target(email: str) -> str:
        normalized = email.strip().lower()
        if not ctx.account_exists(normalized):
            raise NotFoundError("Conta não encontrada.")
        return normalized

    def protect_admins(email: str, actor: str) -> None:
        if email in settings.admin_emails or email == actor:
            raise DiggerError("Administradores não podem ser suspensos nem excluídos por aqui.")

    def audit(actor: str, action: str, email: str = "") -> None:
        logger.info("admin_action actor={} action={} target={}", actor, action, email or "-")

    # -- quem sou eu ------------------------------------------------------------------------------
    @app.get("/api/admin/session")
    def admin_session(request: Request) -> dict[str, Any]:
        """Diz se a sessao atual e de administrador (a interface mostra a aba so para quem e). Nunca da erro."""
        if not ctx.admin_token and not settings.admin_emails:
            return {"admin": False}
        actor = actor_of(request)
        return {"admin": actor is not None, "email": actor if actor and actor != "token" else None}

    # -- visao geral e sistema --------------------------------------------------------------------------
    @app.get("/api/admin/overview")
    def admin_overview(request: Request) -> dict[str, Any]:
        require_admin(request)
        return admin.overview()

    @app.get("/api/admin/system")
    def admin_system(request: Request) -> dict[str, Any]:
        require_admin(request)
        return {
            "database": admin.database_kind(), "billingEnforced": settings.billing_enforced, "pixConfigured": bool(settings.pix_key),
            "mailEnabled": ctx.mailer is not None, "termsRequired": settings.require_terms,
            "legalComplete": bool(settings.legal_controller and settings.legal_contact), "production": settings.production,
            "adminEmails": list(settings.admin_emails), "tokenEnabled": bool(ctx.admin_token), "usage": ctx.usage_snapshot(),
        }

    # -- usuarios --------------------------------------------------------------------------------------------
    @app.get("/api/admin/users")
    def admin_users(request: Request, q: str = Query("", max_length=100), offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)) -> dict[str, Any]:
        require_admin(request)
        return admin.users(q, offset, limit)

    @app.get("/api/admin/users/{email}")
    def admin_user(email: str, request: Request) -> dict[str, Any]:
        require_admin(request)
        found = admin.user(email.strip().lower())
        if found is None:
            raise NotFoundError("Conta não encontrada.")
        found["isAdmin"] = found["email"] in settings.admin_emails
        return found

    @app.post("/api/admin/users/{email}/suspend")
    def admin_suspend(email: str, body: ReasonIn, request: Request) -> dict[str, bool]:
        actor = require_admin(request)
        address = target(email)
        protect_admins(address, actor)
        if ctx.flags is None:
            raise DiggerError("Suspensão indisponível.")
        ctx.flags.suspend(address, body.reason)
        ctx.session_changed(address, False)
        audit(actor, "suspend", address)
        return {"suspended": True}

    @app.post("/api/admin/users/{email}/unsuspend")
    def admin_unsuspend(email: str, request: Request) -> dict[str, bool]:
        actor = require_admin(request)
        address = target(email)
        if ctx.flags is None:
            raise DiggerError("Suspensão indisponível.")
        changed = ctx.flags.unsuspend(address)
        ctx.session_changed(address, True)
        audit(actor, "unsuspend", address)
        return {"unsuspended": changed}

    @app.post("/api/admin/users/{email}/reset-password")
    def admin_reset_password(email: str, request: Request) -> dict[str, bool]:
        """Manda ao dono da conta o link de redefinicao de senha (o administrador nunca ve nem define a senha)."""
        actor = require_admin(request)
        address = target(email)
        sent = ctx.send_reset(address)
        audit(actor, "send_reset_link", address)
        if not sent and ctx.mailer is not None:
            return {"sent": False}  # ja ha um link recente (1 por minuto)
        if ctx.mailer is None:
            raise DiggerError("O envio de e-mails não está configurado neste servidor.")
        return {"sent": True}

    @app.post("/api/admin/users/{email}/verify")
    def admin_verify(email: str, request: Request) -> dict[str, bool]:
        actor = require_admin(request)
        address = target(email)
        ctx.mark_verified(address)
        audit(actor, "mark_verified", address)
        return {"verified": True}

    @app.delete("/api/admin/users/{email}")
    def admin_delete_user(email: str, body: ConfirmDeleteIn, request: Request) -> dict[str, bool]:
        """Exclui a conta e todos os dados dela (pedido do titular, LGPD). Pede o e-mail de novo para evitar engano."""
        actor = require_admin(request)
        address = target(email)
        protect_admins(address, actor)
        if body.confirm.strip().lower() != address:
            raise DiggerError("Digite o e-mail da conta para confirmar a exclusão.")
        ctx.purge_account(address)
        ctx.session_changed(address, False)
        audit(actor, "delete_account", address)
        return {"deleted": True}

    # -- pagamentos --------------------------------------------------------------------------------------------
    @app.get("/api/admin/billing/requests")
    def admin_requests(request: Request, status: str = Query(PENDING, max_length=20)) -> dict[str, Any]:
        require_admin(request)
        items = billing.confirmed(100) if status == CONFIRMED else billing.pending() if status == PENDING else []
        return {"requests": [{**admin.payment(item), "planName": catalog[item.plan].name if item.plan in catalog else item.plan,
                              "amount": ctx.money(item.amount_cents), "reference": item.reference} for item in items]}

    @app.post("/api/admin/billing/requests/{request_id}/confirm")
    def admin_confirm(request_id: str, body: NoteIn, request: Request) -> dict[str, Any]:
        actor = require_admin(request)
        subscription = billing.confirm(request_id, body.note)
        audit(actor, "confirm_payment", subscription.email)
        if ctx.mailer is not None:
            try:
                ctx.mailer.send(EmailMessage(
                    subscription.email, "Sua assinatura foi ativada",
                    f"Olá!\n\nRecebemos o seu pagamento: o plano {catalog[subscription.plan].name} está ativo até "
                    f"{subscription.expires_at.strftime('%d/%m/%Y')}.\n\nObrigado por apoiar o Nexus Science.\n",
                ))
            except MailError as error:
                logger.warning("Falha ao avisar a ativacao da assinatura: {}", error)
        return {"confirmed": True, "email": subscription.email, "plan": subscription.plan,
                "expiresAt": subscription.expires_at.isoformat(timespec="seconds")}

    @app.post("/api/admin/billing/requests/{request_id}/cancel")
    def admin_cancel(request_id: str, request: Request) -> dict[str, bool]:
        actor = require_admin(request)
        if not billing.cancel(request_id):
            raise NotFoundError("Pedido não encontrado ou já tratado.")
        audit(actor, "cancel_payment_request", request_id)
        return {"cancelled": True}

    @app.post("/api/admin/billing/grant")
    def admin_grant(body: GrantIn, request: Request) -> dict[str, Any]:
        actor = require_admin(request)
        if body.plan not in catalog or body.plan == plans.FREE_KEY:
            raise DiggerError("Plano inválido.")
        address = target(body.email)
        subscription = billing.grant(address, body.plan, body.days)
        audit(actor, f"grant_{body.plan}_{body.days}d", address)
        return {"email": address, "plan": subscription.plan, "expiresAt": subscription.expires_at.isoformat(timespec="seconds")}

    @app.post("/api/admin/billing/revoke")
    def admin_revoke(body: EmailIn, request: Request) -> dict[str, bool]:
        actor = require_admin(request)
        address = body.email.strip().lower()
        removed = billing.revoke(address)
        audit(actor, "revoke_subscription", address)
        return {"revoked": removed}
