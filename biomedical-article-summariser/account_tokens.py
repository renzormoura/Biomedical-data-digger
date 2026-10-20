"""Tokens de uso unico das contas (redefinir senha, confirmar e-mail) e o estado de confirmacao do e-mail.

O token enviado por e-mail e aleatorio (32 bytes); no banco fica apenas o **hash SHA-256**, entao um vazamento do banco nao
entrega links validos. Cada token vale para um proposito (`reset` ou `verify`), expira e e apagado ao ser usado.
Emitir um token novo apaga os anteriores do mesmo e-mail e proposito.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from db import Database
from timeutil import Clock, iso, utcnow

RESET = "reset"
VERIFY = "verify"
TTL = {RESET: timedelta(hours=1), VERIFY: timedelta(hours=48)}

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS account_tokens (
        token_hash TEXT PRIMARY KEY, email TEXT NOT NULL, purpose TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS idx_account_tokens_email ON account_tokens (email, purpose)",
    "CREATE TABLE IF NOT EXISTS email_verification (email TEXT PRIMARY KEY, verified_at TEXT NOT NULL)",
)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AccountTokens:
    def __init__(self, database: Database | None = None, clock: Clock = utcnow) -> None:
        self._db = database or Database()
        self._clock = clock

    def initialize(self) -> None:
        with self._db.transaction() as tx:
            for statement in _SCHEMA:
                tx.execute(statement)

    def now(self) -> datetime:
        """Hora segundo o relogio dos tokens (os prazos de validade e de reenvio usam o mesmo relogio)."""
        return self._clock()

    def issue(self, email: str, purpose: str) -> str:
        """Gera um token novo (o texto que vai no link) e apaga os anteriores do mesmo e-mail e proposito."""
        now = self._clock()
        raw = secrets.token_urlsafe(32)
        with self._db.transaction() as tx:
            tx.execute("DELETE FROM account_tokens WHERE email = ? AND purpose = ?", (email, purpose))
            tx.execute(
                "INSERT INTO account_tokens (token_hash, email, purpose, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
                (_hash(raw), email, purpose, iso(now + TTL[purpose]), iso(now)),
            )
        return raw

    def peek(self, raw: str, purpose: str) -> str | None:
        """E-mail dono do token valido (existe, do proposito certo e nao expirado), sem consumi-lo."""
        rows = self._db.query(
            "SELECT email, expires_at FROM account_tokens WHERE token_hash = ? AND purpose = ?", (_hash(raw or ""), purpose),
        )
        if not rows or str(rows[0][1]) < iso(self._clock()):
            return None
        return str(rows[0][0])

    def consume(self, raw: str, purpose: str) -> str | None:
        """Como `peek`, mas apaga o token (uso unico). Devolve o e-mail ou `None`."""
        email = self.peek(raw, purpose)
        if email is not None:
            self._db.execute("DELETE FROM account_tokens WHERE token_hash = ?", (_hash(raw),))
        return email

    def last_issued(self, email: str, purpose: str) -> datetime | None:
        """Quando foi emitido o token mais recente (para limitar reenvios)."""
        rows = self._db.query(
            "SELECT created_at FROM account_tokens WHERE email = ? AND purpose = ? ORDER BY created_at DESC", (email, purpose),
        )
        return datetime.fromisoformat(str(rows[0][0])) if rows else None

    def clear(self, email: str, purpose: str) -> None:
        self._db.execute("DELETE FROM account_tokens WHERE email = ? AND purpose = ?", (email, purpose))

    def mark_verified(self, email: str) -> None:
        self._db.execute(
            "INSERT INTO email_verification (email, verified_at) VALUES (?, ?) ON CONFLICT (email) DO NOTHING", (email, iso(self._clock())),
        )

    def is_verified(self, email: str) -> bool:
        return bool(self._db.query("SELECT 1 FROM email_verification WHERE email = ?", (email,)))

    def delete_user_data(self, email: str) -> None:
        with self._db.transaction() as tx:
            tx.execute("DELETE FROM account_tokens WHERE email = ?", (email,))
            tx.execute("DELETE FROM email_verification WHERE email = ?", (email,))
