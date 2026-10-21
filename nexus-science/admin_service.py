"""Consultas do painel de administracao: visao geral, lista de usuarios com plano e uso, e o detalhe de uma conta.

So le (as acoes ficam nas rotas, que chamam os armazens de cada assunto). Faz as contagens direto em SQL para a lista de 50 contas
nao carregar a biblioteca de ninguem na memoria.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import plans
from account_consent import ConsentStore
from account_flags import AccountFlags
from account_tokens import AccountTokens
from billing import PENDING, BillingStore, PaymentRequest
from db import Database
from timeutil import Clock, utcnow


def _created(value: Any) -> str:
    """Data de criacao da conta no mesmo formato nos dois bancos (PostgreSQL devolve `datetime`, SQLite devolve texto)."""
    if isinstance(value, datetime):
        return (value.astimezone(timezone.utc) if value.tzinfo else value).strftime("%Y-%m-%dT%H:%M:%S")
    return str(value)[:19].replace(" ", "T")


def _like(query: str) -> str:
    return "%" + query.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class AdminService:
    def __init__(
        self, database: Database, billing: BillingStore, tokens: AccountTokens, consent: ConsentStore, flags: AccountFlags,
        clock: Clock = utcnow,
    ) -> None:
        self._db = database
        self._billing, self._tokens, self._consent, self._flags = billing, tokens, consent, flags
        self._clock = clock

    def database_kind(self) -> str:
        return "PostgreSQL" if self._db.uses_postgres else "SQLite"

    def _count(self, sql: str, params: tuple[object, ...] = ()) -> int:
        return int(self._db.query(sql, params)[0][0])

    # -- visao geral ------------------------------------------------------------------------------
    def overview(self) -> dict[str, Any]:
        now = self._clock()
        total = self._count("SELECT COUNT(*) FROM users")
        active = self._db.query("SELECT plan, COUNT(*) FROM subscriptions WHERE expires_at > ? GROUP BY plan", (now.isoformat(timespec="seconds"),))
        by_plan = dict.fromkeys(plans.PAID_KEYS, 0)
        by_plan.update({str(plan): int(count) for plan, count in active})
        paying = sum(by_plan.values())
        month_ago = now - timedelta(days=30)
        return {
            "users": total,
            "verified": self._count("SELECT COUNT(*) FROM email_verification"),
            "suspended": self._count("SELECT COUNT(*) FROM suspended_accounts"),
            "byPlan": {plans.FREE_KEY: total - paying, **by_plan},
            "newLast7Days": self._count("SELECT COUNT(*) FROM users WHERE created_at >= ?", ((now - timedelta(days=7)).isoformat(),)),
            "pendingPayments": len(self._billing.pending()),
            "revenueLast30DaysCents": self._billing.revenue_cents(month_ago),
            "revenueTotalCents": self._billing.revenue_cents(),
            "expiringSoon": self._count(
                "SELECT COUNT(*) FROM subscriptions WHERE expires_at > ? AND expires_at <= ?",
                (now.isoformat(timespec="seconds"), (now + timedelta(days=7)).isoformat(timespec="seconds")),
            ),
        }

    # -- usuarios -------------------------------------------------------------------------------------
    def users(self, query: str = "", offset: int = 0, limit: int = 25) -> dict[str, Any]:
        like, limit = _like(query), max(1, min(limit, 100))
        total = self._count("SELECT COUNT(*) FROM users WHERE email LIKE ? ESCAPE '\\'", (like,))
        rows = self._db.query(
            "SELECT u.email, u.created_at, s.plan, s.expires_at, "
            "(SELECT COUNT(*) FROM email_verification v WHERE v.email = u.email), "
            "(SELECT COUNT(*) FROM suspended_accounts x WHERE x.email = u.email), "
            "(SELECT COUNT(*) FROM library_items l WHERE l.user_email = u.email), "
            "(SELECT COUNT(*) FROM reading_lists r WHERE r.owner_email = u.email), "
            "(SELECT COUNT(*) FROM reports p WHERE p.owner_email = u.email) "
            "FROM users u LEFT JOIN subscriptions s ON s.email = u.email WHERE u.email LIKE ? ESCAPE '\\' "
            "ORDER BY u.email LIMIT ? OFFSET ?", (like, limit, max(0, offset)),
        )
        now = self._clock()
        users = []
        for email, created, plan, expires, verified, suspended, library, lists, reports in rows:
            active = bool(plan and expires and datetime.fromisoformat(str(expires)) > now)
            users.append({
                "email": str(email), "createdAt": _created(created), "plan": str(plan) if active else plans.FREE_KEY,
                "expiresAt": str(expires) if active else "", "verified": bool(verified), "suspended": bool(suspended),
                "usage": {"library": int(library), "lists": int(lists), "reports": int(reports)},
            })
        return {"users": users, "total": total, "offset": max(0, offset), "limit": limit}

    def user(self, email: str) -> dict[str, Any] | None:
        listed = self.users(email, 0, 100)["users"]
        base = next((u for u in listed if u["email"] == email), None)
        if base is None:
            return None
        terms = self._consent.get(email)
        suspension = self._flags.get(email)
        base["terms"] = {"version": terms[0], "acceptedAt": terms[1]} if terms else None
        base["suspension"] = {"reason": suspension[0], "since": suspension[1]} if suspension else None
        base["payments"] = [self.payment(item) for item in self._billing.requests(email)]
        return base

    @staticmethod
    def payment(item: PaymentRequest) -> dict[str, Any]:
        return {"id": item.id, "plan": item.plan, "months": item.months, "amountCents": item.amount_cents, "status": item.status,
                "createdAt": item.created_at, "confirmedAt": item.confirmed_at, "note": item.note, "email": item.email,
                "pending": item.status == PENDING}
