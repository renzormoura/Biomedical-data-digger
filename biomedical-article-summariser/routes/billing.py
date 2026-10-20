"""Rotas: planos, assinatura e pagamento por Pix, do lado da pessoa (a conciliacao do administrador esta em `routes/admin.py`).

Ver os planos, pedir uma assinatura (recebe o Pix "copia e cola") e acompanhar ou cancelar o pedido.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from pydantic import BaseModel, Field

import plans
from billing import PENDING, PaymentRequest, Subscription
from domain import DiggerError, NotFoundError, SourceUnavailableError
from pix import br_code
from routes.context import ApiContext


class RequestIn(BaseModel):
    plan: str = Field(max_length=20)
    months: int = Field(ge=1, le=24)


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
            "months": item.months, "amountCents": item.amount_cents, "amount": plans.money(item.amount_cents),
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
            "plans": [{"key": p.key, "name": p.name, "description": p.description, "priceCents": p.price_cents, "price": plans.money(p.price_cents),
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
