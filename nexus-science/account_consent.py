"""Registro do aceite dos Termos de Uso e da Politica de Privacidade (qual versao, quando) por conta."""

from __future__ import annotations

from db import Database
from timeutil import Clock, iso, utcnow

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS terms_acceptance (email TEXT PRIMARY KEY, version TEXT NOT NULL, accepted_at TEXT NOT NULL)",
)


class ConsentStore:
    def __init__(self, database: Database | None = None, clock: Clock = utcnow) -> None:
        self._db = database or Database()
        self._clock = clock

    def initialize(self) -> None:
        with self._db.transaction() as tx:
            for statement in _SCHEMA:
                tx.execute(statement)

    def record(self, email: str, version: str) -> None:
        """Guarda (ou atualiza) a versao aceita e o momento do aceite."""
        self._db.execute(
            "INSERT INTO terms_acceptance (email, version, accepted_at) VALUES (?, ?, ?) "
            "ON CONFLICT (email) DO UPDATE SET version = excluded.version, accepted_at = excluded.accepted_at",
            (email, version, iso(self._clock())),
        )

    def get(self, email: str) -> tuple[str, str] | None:
        """`(versao, aceito_em)` ou `None` se a conta nunca registrou aceite (contas anteriores a esta funcao)."""
        rows = self._db.query("SELECT version, accepted_at FROM terms_acceptance WHERE email = ?", (email,))
        return (str(rows[0][0]), str(rows[0][1])) if rows else None

    def delete_user_data(self, email: str) -> None:
        self._db.execute("DELETE FROM terms_acceptance WHERE email = ?", (email,))
