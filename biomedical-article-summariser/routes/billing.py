"""Rotas: planos, assinatura e pagamento por Pix (pessoa) e conciliacao (administrador).

Pessoa: ver os planos, pedir uma assinatura (recebe o Pix "copia e cola") e acompanhar o pedido.
Administrador (`Authorization: Bearer ADMIN_TOKEN`): ver pedidos pendentes e contas, confirmar um pagamento depois de conferir
o extrato, cancelar, conceder cortesia ou revogar. Nada aqui cobra sozinho: a confirmacao e sempre um ato do administrador.
"""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field

import plans
from billing import PENDING, PaymentRequest, Subscription
from domain import DiggerError, NotFoundError, RateLimitedError, SourceUnavailableError
from mailer import EmailMessage, MailError
from pix import br_code
from ratelimit import RateLimitExceeded
from routes.context import ApiContext


class RequestIn(BaseModel):
    plan: str = Field(max_length=20)
    months: int = Field(ge=1, le=24)


class NoteIn(BaseModel):
    note: str = Field("", max_length=300)


class GrantIn(BaseModel):
    email: str = Field(max_length=320)
    plan: str = Field(max_length=20)
    days: int = Field(ge=1, le=3660)


class EmailIn(BaseModel):
    email: str = Field(max_length=320)


class AdminUnauthorizedError(Exception):
    """Token de administrador ausente ou errado (vira 401 sem detalhes)."""


def money(cents: int) -> str:
    return f"R$ {cents // 100:,}".replace(",", ".") + f",{cents % 100:02d}"


def register_billing_routes(app: FastAPI, ctx: ApiContext) -> None:
    billing, settings = ctx.billing, ctx.settings
    if billing is None or settings is None:
        return
    catalog = plans.catalog(settings)
    pix_ready = bool(settings.pix_key)

    def limits_payload(plan: plans.Plan) -> dict[str, int]:
        return {"library": plan.library, "lists": plan.lists, "reports": plan.reports}

    def request_payload(item: PaymentRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": item.id, "plan": item.plan, "planName": catalog[item.plan].name if item.plan in catalog else item.plan,
            "months": item.months, "amountCents": item.amount_cents, "amount": money(item.amount_cents),
            "reference": item.reference, "status": item.status, "createdAt": item.created_at, "confirmedAt": item.confirmed_at,
        }
        if item.status == PENDING and pix_ready:
            payload["pix"] = {
                "copyPaste": br_code(settings.pix_key, settings.pix_name, settings.pix_city, item.amount_cents, item.reference),
                "key": settings.pix_key, "name": settings.pix_name,
            }
        return payload

    def subscription_payload(email: str) -> dict[str, Any]:
        current: Subscription | None = billing.subscription(email)
        key = ctx.plan_for(email).key
        return {
            "plan": key, "planName": catalog[key].name, "expiresAt": current.expires_at.isoformat(timespec="seconds") if current else None,
            "active": key != plans.FREE_KEY,
        }

    # -- pessoa ---------------------------------------------------------------------------------
    @app.get("/api/billing/plans")
    def list_plans() -> dict[str, Any]:
        return {
            "enforced": settings.billing_enforced, "pixAvailable": pix_ready, "periods": list(plans.PERIODS),
            "plans": [{"key": p.key, "name": p.name, "description": p.description, "priceCents": p.price_cents, "price": money(p.price_cents),
                       "limits": limits_payload(p)} for p in catalog.values()],
        }

    @app.get("/api/billing/me")
    def my_billing(request: Request) -> dict[str, Any]:
        user = ctx.require_user(request)
        plan = ctx.plan_for(user)
        return {
            **subscription_payload(user), "enforced": settings.billing_enforced, "limits": limits_payload(plan), "usage": ctx.usage_for(user),
            "requests": [request_payload(item) for item in billing.requests(user)],
        }

    @app.post("/api/billing/requests")
    def create_request(body: RequestIn, request: Request) -> dict[str, Any]:
        user = ctx.require_user(request)
        if not pix_ready:
            raise SourceUnavailableError("O pagamento por Pix ainda não está disponível. Fale com o suporte.")
        plan = catalog.get(body.plan)
        if plan is None or plan.price_cents <= 0:
            raise DiggerError("Plano inválido.")
        if body.months not in plans.PERIODS:
            raise DiggerError("Período inválido.")
        return request_payload(billing.create_request(user, plan.key, body.months, plans.amount_cents(plan, body.months)))

    @app.delete("/api/billing/requests/{request_id}")
    def cancel_my_request(request_id: str, request: Request) -> dict[str, bool]:
        user = ctx.require_user(request)
        if not billing.cancel(request_id, email=user):
            raise NotFoundError("Pedido não encontrado ou já tratado.")
        return {"cancelled": True}

    # -- administrador ---------------------------------------------------------------------------
    def require_admin(request: Request) -> None:
        if not ctx.admin_token:
            raise NotFoundError("Não encontrado.")
        try:
            ctx.admin_limiter.check(ctx.identity(request))
        except RateLimitExceeded as error:
            raise RateLimitedError(str(error)) from error
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(supplied.encode(), f"Bearer {ctx.admin_token}".encode()):
            raise AdminUnauthorizedError

    @app.exception_handler(AdminUnauthorizedError)
    async def unauthorized(request: Request, error: AdminUnauthorizedError) -> JSONResponse:
        return JSONResponse({"error": "Não autorizado."}, status_code=401)

    def notify_activated(subscription: Subscription) -> None:
        if ctx.mailer is None:
            return
        try:
            ctx.mailer.send(EmailMessage(
                subscription.email, "Sua assinatura foi ativada",
                f"Olá!\n\nRecebemos o seu pagamento: o plano {catalog[subscription.plan].name} está ativo até "
                f"{subscription.expires_at.strftime('%d/%m/%Y')}.\n\nObrigado por apoiar o Biomedical Data Digger.\n",
            ))
        except MailError as error:
            logger.warning("Falha ao avisar a ativacao da assinatura: {}", error)

    @app.get("/api/admin/billing/requests")
    def admin_requests(request: Request, status: str = Query(PENDING, max_length=20)) -> dict[str, Any]:
        require_admin(request)
        items = billing.pending() if status == PENDING else []
        return {"requests": [{**request_payload(item), "email": item.email} for item in items]}

    @app.post("/api/admin/billing/requests/{request_id}/confirm")
    def admin_confirm(request_id: str, body: NoteIn, request: Request) -> dict[str, Any]:
        require_admin(request)
        subscription = billing.confirm(request_id, body.note)
        notify_activated(subscription)
        return {"confirmed": True, "email": subscription.email, "plan": subscription.plan,
                "expiresAt": subscription.expires_at.isoformat(timespec="seconds")}

    @app.post("/api/admin/billing/requests/{request_id}/cancel")
    def admin_cancel(request_id: str, request: Request) -> dict[str, bool]:
        require_admin(request)
        if not billing.cancel(request_id):
            raise NotFoundError("Pedido não encontrado ou já tratado.")
        return {"cancelled": True}

    @app.get("/api/admin/accounts")
    def admin_accounts(request: Request, q: str = Query("", max_length=100)) -> dict[str, Any]:
        require_admin(request)
        return {"accounts": billing.accounts(q)}

    @app.post("/api/admin/billing/grant")
    def admin_grant(body: GrantIn, request: Request) -> dict[str, Any]:
        require_admin(request)
        if body.plan not in catalog or body.plan == plans.FREE_KEY:
            raise DiggerError("Plano inválido.")
        email = body.email.strip().lower()
        if not ctx.account_exists(email):
            raise NotFoundError("Conta não encontrada.")
        subscription = billing.grant(email, body.plan, body.days)
        return {"email": email, "plan": subscription.plan, "expiresAt": subscription.expires_at.isoformat(timespec="seconds")}

    @app.post("/api/admin/billing/revoke")
    def admin_revoke(body: EmailIn, request: Request) -> dict[str, bool]:
        require_admin(request)
        return {"revoked": billing.revoke(body.email.strip().lower())}

