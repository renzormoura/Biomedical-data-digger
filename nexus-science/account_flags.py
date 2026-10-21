"""Contas suspensas pelo administrador (abuso, fraude, pedido da pessoa). Suspensa, a conta nao entra nem usa a sessao aberta; nada e apagado."""

from __future__ import annotations

from db import Database
from timeutil import Clock, iso, utcnow

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS suspended_accounts (email TEXT PRIMARY KEY, reason TEXT NOT NULL, suspended_at TEXT NOT NULL)",
)


class AccountFlags:
    def __init__(self, database: Database | None = None, clock: Clock = utcnow) -> None:
        self._db = database or Database()
        self._clock = clock

    def initialize(self) -> None:
        with self._db.transaction() as tx:
            for statement in _SCHEMA:
                tx.execute(statement)

    def suspend(self, email: str, reason: str = "") -> None:
        self._db.execute(
            "INSERT INTO suspended_accounts (email, reason, suspended_at) VALUES (?, ?, ?) "
            "ON CONFLICT (email) DO UPDATE SET reason = excluded.reason, suspended_at = excluded.suspended_at",
            (email, reason[:300], iso(self._clock())),
        )

    def unsuspend(self, email: str) -> bool:
        return self._db.execute("DELETE FROM suspended_accounts WHERE email = ?", (email,)) > 0

    def get(self, email: str) -> tuple[str, str] | None:
        """`(motivo, desde_quando)` se a conta esta suspensa."""
        rows = self._db.query("SELECT reason, suspended_at FROM suspended_accounts WHERE email = ?", (email,))
        return (str(rows[0][0]), str(rows[0][1])) if rows else None

    def is_suspended(self, email: str) -> bool:
        return self.get(email) is not None

    def delete_user_data(self, email: str) -> None:
        self.unsuspend(email)
