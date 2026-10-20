"""Assinaturas e pedidos de pagamento (Pix, conciliado pelo administrador).

Fluxo: a pessoa cria um **pedido** (plano + meses) e paga o Pix com o identificador do pedido; o administrador confere o extrato
e **confirma** o pedido, o que ativa (ou prorroga) a assinatura. Sem confirmar, nada muda. A assinatura e so `plano + validade`;
vencida, a conta volta ao plano gratuito sem perder dados (os limites passam a valer so para novas gravacoes).

Pedidos confirmados sao registros de pagamento (obrigacao fiscal e contabil): ficam mesmo depois da exclusao da conta.
"""

from __future__ import annotations

import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from db import Database
from domain import DiggerError, LimitReachedError, NotFoundError
from plans import DAYS_PER_MONTH, FREE_KEY
from timeutil import Clock, iso, utcnow

PENDING, CONFIRMED, CANCELLED = "pendente", "confirmado", "cancelado"
MAX_PENDING = 3
REFERENCE_ALPHABET = string.ascii_uppercase + string.digits

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS subscriptions (email TEXT PRIMARY KEY, plan TEXT NOT NULL, expires_at TEXT NOT NULL, updated_at TEXT NOT NULL)",
    """CREATE TABLE IF NOT EXISTS payment_requests (
        id TEXT PRIMARY KEY, email TEXT NOT NULL, plan TEXT NOT NULL, months INTEGER NOT NULL, amount_cents INTEGER NOT NULL,
        reference TEXT NOT NULL UNIQUE, status TEXT NOT NULL, created_at TEXT NOT NULL, confirmed_at TEXT, note TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS idx_payment_requests_email ON payment_requests (email, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_payment_requests_status ON payment_requests (status, created_at)",
)


@dataclass(frozen=True)
class PaymentRequest:
    id: str
    email: str
    plan: str
    months: int
    amount_cents: int
    reference: str  # identificador que vai no Pix (txid)
    status: str
    created_at: str
    confirmed_at: str | None
    note: str


@dataclass(frozen=True)
class Subscription:
    email: str
    plan: str
    expires_at: datetime

    def active(self, now: datetime) -> bool:
        return self.expires_at > now


def _created(value: Any) -> str:
    """Data de criacao da conta no mesmo formato nos dois bancos (PostgreSQL devolve `datetime`, SQLite devolve texto)."""
    if isinstance(value, datetime):
        return (value.astimezone(timezone.utc) if value.tzinfo else value).strftime("%Y-%m-%dT%H:%M:%S")
    return str(value)[:19].replace(" ", "T")


def _request(row: tuple[Any, ...]) -> PaymentRequest:
    return PaymentRequest(str(row[0]), str(row[1]), str(row[2]), int(row[3]), int(row[4]), str(row[5]), str(row[6]), str(row[7]),
                          str(row[8]) if row[8] else None, str(row[9]))


_COLUMNS = "id, email, plan, months, amount_cents, reference, status, created_at, confirmed_at, note"


class BillingStore:
    def __init__(self, database: Database | None = None, clock: Clock = utcnow) -> None:
        self._db = database or Database()
        self._clock = clock

    def initialize(self) -> None:
        with self._db.transaction() as tx:
            for statement in _SCHEMA:
                tx.execute(statement)

    # -- assinatura ------------------------------------------------------------------------
    def subscription(self, email: str) -> Subscription | None:
        rows = self._db.query("SELECT plan, expires_at FROM subscriptions WHERE email = ?", (email,))
        return Subscription(email, str(rows[0][0]), datetime.fromisoformat(str(rows[0][1]))) if rows else None

    def plan_key(self, email: str) -> str:
        """Plano em vigor: o da assinatura enquanto valida; senao, o gratuito."""
        current = self.subscription(email)
        return current.plan if current and current.active(self._clock()) else FREE_KEY

    def _set_subscription(self, email: str, plan: str, expires_at: datetime) -> Subscription:
        self._db.execute(
            "INSERT INTO subscriptions (email, plan, expires_at, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (email) DO UPDATE SET plan = excluded.plan, expires_at = excluded.expires_at, updated_at = excluded.updated_at",
            (email, plan, iso(expires_at), iso(self._clock())),
        )
        return Subscription(email, plan, expires_at)

    def grant(self, email: str, plan: str, days: int) -> Subscription:
        """Cortesia ou ajuste manual: `plan` por `days` dias a partir de agora (ou do vencimento atual, se for o mesmo plano)."""
        return self._set_subscription(email, plan, self._extend(email, plan, timedelta(days=days)))

    def revoke(self, email: str) -> bool:
        return self._db.execute("DELETE FROM subscriptions WHERE email = ?", (email,)) > 0

    def _extend(self, email: str, plan: str, delta: timedelta) -> datetime:
        now = self._clock()
        current = self.subscription(email)
        base = current.expires_at if current and current.plan == plan and current.active(now) else now
        return base + delta

    # -- pedidos --------------------------------------------------------------------------------
    def create_request(self, email: str, plan: str, months: int, amount_cents: int) -> PaymentRequest:
        """Cria o pedido (ou devolve o pendente identico, para nao acumular). No maximo `MAX_PENDING` pendentes por conta."""
        pending = [r for r in self.requests(email) if r.status == PENDING]
        for existing in pending:
            if existing.plan == plan and existing.months == months and existing.amount_cents == amount_cents:
                return existing
        if len(pending) >= MAX_PENDING:
            raise LimitReachedError("Você já tem pedidos de pagamento em aberto. Cancele algum ou aguarde a confirmação.")
        request = PaymentRequest(
            secrets.token_hex(16), email, plan, months, amount_cents,
            "BDD" + "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(10)), PENDING,
            self._clock().isoformat(timespec="microseconds"), None, "",  # microssegundos: a ordem dos pedidos nao empata
        )
        self._db.execute(
            f"INSERT INTO payment_requests ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",  # noqa: S608 - colunas fixas
            (request.id, request.email, request.plan, request.months, request.amount_cents, request.reference, request.status,
             request.created_at, None, ""),
        )
        return request

    def requests(self, email: str) -> list[PaymentRequest]:
        rows = self._db.query(f"SELECT {_COLUMNS} FROM payment_requests WHERE email = ? ORDER BY created_at DESC", (email,))  # noqa: S608
        return [_request(row) for row in rows]

    def pending(self) -> list[PaymentRequest]:
        rows = self._db.query(f"SELECT {_COLUMNS} FROM payment_requests WHERE status = ? ORDER BY created_at", (PENDING,))  # noqa: S608
        return [_request(row) for row in rows]

    def get(self, request_id: str) -> PaymentRequest | None:
        rows = self._db.query(f"SELECT {_COLUMNS} FROM payment_requests WHERE id = ?", (request_id,))  # noqa: S608
        return _request(rows[0]) if rows else None

    def cancel(self, request_id: str, email: str | None = None) -> bool:
        """Cancela um pedido pendente (a pessoa so cancela os proprios; o administrador, qualquer um)."""
        if email:
            return self._db.execute("UPDATE payment_requests SET status = ? WHERE id = ? AND status = ? AND email = ?",
                                    (CANCELLED, request_id, PENDING, email)) > 0
        return self._db.execute("UPDATE payment_requests SET status = ? WHERE id = ? AND status = ?", (CANCELLED, request_id, PENDING)) > 0

    def confirm(self, request_id: str, note: str = "") -> Subscription:
        """Confirma o pagamento de um pedido pendente e ativa ou prorroga a assinatura."""
        request = self.get(request_id)
        if request is None or request.status != PENDING:
            raise NotFoundError("Pedido não encontrado ou já tratado.")
        changed = self._db.execute(
            "UPDATE payment_requests SET status = ?, confirmed_at = ?, note = ? WHERE id = ? AND status = ?",
            (CONFIRMED, iso(self._clock()), note[:300], request_id, PENDING),
        )
        if not changed:  # outra confirmacao simultanea ja tratou este pedido
            raise NotFoundError("Pedido não encontrado ou já tratado.")
        expires = self._extend(request.email, request.plan, timedelta(days=DAYS_PER_MONTH * request.months))
        return self._set_subscription(request.email, request.plan, expires)

    # -- administracao ----------------------------------------------------------------------------
    def accounts(self, query: str = "", limit: int = 50) -> list[dict[str, str]]:
        """Contas com o plano e a validade (so para o painel de administracao)."""
        like = "%" + query.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        rows = self._db.query(
            "SELECT u.email, u.created_at, s.plan, s.expires_at FROM users u LEFT JOIN subscriptions s ON s.email = u.email "
            "WHERE u.email LIKE ? ESCAPE '\\' ORDER BY u.email LIMIT ?", (like, max(1, min(limit, 200))),
        )
        now = self._clock()
        out = []
        for email, created, plan, expires in rows:
            active = bool(plan and expires and datetime.fromisoformat(str(expires)) > now)
            out.append({"email": str(email), "createdAt": _created(created), "plan": str(plan) if active else FREE_KEY,
                        "expiresAt": str(expires) if expires else "", "active": "1" if active else "0"})
        return out

    def delete_user_data(self, email: str) -> None:
        """Apaga a assinatura e os pedidos nao confirmados; os confirmados ficam (registro de pagamento)."""
        with self._db.transaction() as tx:
            tx.execute("DELETE FROM subscriptions WHERE email = ?", (email,))
            tx.execute("DELETE FROM payment_requests WHERE email = ? AND status <> ?", (email, CONFIRMED))


def require_months(months: int, allowed: tuple[int, ...]) -> int:
    if months not in allowed:
        raise DiggerError("Período inválido.")
    return months
