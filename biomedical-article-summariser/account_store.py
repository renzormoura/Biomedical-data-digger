"""Persistencia de contas com PostgreSQL em producao e SQLite localmente."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from functools import lru_cache

from dotenv import load_dotenv

from db import Database
from timeutil import utcnow

load_dotenv()

_PASSWORD_ITERATIONS = 600_000
_DEFAULT_SQLITE_PATH = os.path.join(os.path.dirname(__file__), "accounts.sqlite3")


_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MAX_EMAIL_LENGTH = 320
_MIN_PASSWORD_LENGTH = 8
_MAX_PASSWORD_LENGTH = 128  # evita DoS por PBKDF2 sobre entradas gigantes
_COMMON_PASSWORDS = frozenset(
    {"12345678", "123456789", "1234567890", "password", "password1", "qwerty123", "11111111", "senha123", "abcd1234"}
)
_DUMMY_SALT = bytes(32)


class AccountStoreError(RuntimeError):
    """Erro operacional do armazenamento de contas."""


class InvalidCredentialsFormat(ValueError):
    """E-mail ou senha fora da politica aceita."""


def validate_credentials(email: str, password: str) -> tuple[str, str]:
    """Normaliza e valida e-mail/senha; retorna o par normalizado."""
    normalized_email = (email or "").strip().lower()
    if len(normalized_email) > _MAX_EMAIL_LENGTH or not _EMAIL_PATTERN.match(normalized_email):
        raise InvalidCredentialsFormat("Informe um e-mail válido.")
    if not password or not password.strip():
        raise InvalidCredentialsFormat("Informe uma senha.")
    password = password.strip()
    if len(password) < _MIN_PASSWORD_LENGTH:
        raise InvalidCredentialsFormat(f"A senha deve ter pelo menos {_MIN_PASSWORD_LENGTH} caracteres.")
    if len(password) > _MAX_PASSWORD_LENGTH:
        raise InvalidCredentialsFormat(f"A senha deve ter no máximo {_MAX_PASSWORD_LENGTH} caracteres.")
    if password.lower() in _COMMON_PASSWORDS or password.lower() == normalized_email:
        raise InvalidCredentialsFormat("Senha muito comum. Escolha outra.")
    return normalized_email, password


class AccountStore:
    """Contas de usuario sobre `db.Database` (o mesmo acesso ao banco dos demais armazens)."""

    def __init__(self, database: Database | None = None) -> None:
        self.database_url = os.environ.get("DATABASE_URL", "").strip()
        self.sqlite_path = os.environ.get("DATABASE_PATH", _DEFAULT_SQLITE_PATH)
        self.environment = os.environ.get("APP_ENV", "development").lower()
        if self.environment == "production" and not self.database_url:
            raise AccountStoreError(
                "DATABASE_URL e obrigatoria em producao. Configure um PostgreSQL persistente no Render."
            )
        self._db = database or Database(database_url=self.database_url, sqlite_path=self.sqlite_path)
        self.uses_postgres = self._db.uses_postgres

    def initialize(self) -> None:
        if self.uses_postgres:
            ddl = (
                "CREATE TABLE IF NOT EXISTS users ("
                "email VARCHAR(320) PRIMARY KEY, password_hash VARCHAR(128) NOT NULL, "
                "password_salt VARCHAR(64) NOT NULL, created_at TIMESTAMPTZ NOT NULL)"
            )
        else:
            ddl = (
                "CREATE TABLE IF NOT EXISTS users ("
                "email TEXT PRIMARY KEY, password_hash TEXT NOT NULL, "
                "password_salt TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
        self._db.execute(ddl)

    @staticmethod
    def _password_digest(password: str, salt: bytes) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            _PASSWORD_ITERATIONS,
        ).hex()

    def create_user(self, email: str, password: str) -> bool:
        normalized_email = email.strip().lower()
        salt = secrets.token_bytes(32)
        password_hash = self._password_digest(password, salt)
        created_at = utcnow()
        stored_at: datetime | str = created_at if self.uses_postgres else created_at.isoformat()
        try:
            self._db.execute(
                "INSERT INTO users (email, password_hash, password_salt, created_at) VALUES (?, ?, ?, ?)",
                (normalized_email, password_hash, salt.hex(), stored_at),
            )
        except Exception as error:
            if self._is_unique_violation(error):
                return False
            raise AccountStoreError("Nao foi possivel salvar a conta.") from error
        return True

    def authenticate(self, email: str, password: str) -> bool:
        row = self._fetch_one("SELECT password_hash, password_salt FROM users WHERE email = ?", (email.strip().lower(),))
        if not row:
            # Gasta o mesmo custo de PBKDF2 para nao revelar, pelo tempo, se o e-mail existe.
            self._password_digest(password, _DUMMY_SALT)
            return False
        stored_hash, stored_salt = row
        calculated_hash = self._password_digest(password, bytes.fromhex(str(stored_salt)))
        return hmac.compare_digest(calculated_hash, str(stored_hash))

    def _fetch_one(self, sql: str, params: tuple[object, ...]) -> tuple[object, ...] | None:
        rows = self._db.query(sql, params)
        return tuple(rows[0]) if rows else None

    def _write(self, sql: str, params: tuple[object, ...]) -> int:
        """Executa uma escrita e devolve quantas linhas foram afetadas."""
        return self._db.execute(sql, params)

    def exists(self, email: str) -> bool:
        return self._fetch_one("SELECT 1 FROM users WHERE email = ?", (email.strip().lower(),)) is not None

    def created_at(self, email: str) -> str:
        """Data de criacao da conta (ISO), ou vazio se a conta nao existe."""
        row = self._fetch_one("SELECT created_at FROM users WHERE email = ?", (email.strip().lower(),))
        if not row:
            return ""
        value = row[0]
        if isinstance(value, datetime):  # PostgreSQL devolve com fuso; normaliza para UTC no mesmo formato do SQLite
            return (value.astimezone(timezone.utc) if value.tzinfo else value).strftime("%Y-%m-%dT%H:%M:%S")
        return str(value)[:19]

    def change_password(self, email: str, new_password: str) -> bool:
        salt = secrets.token_bytes(32)
        digest = self._password_digest(new_password, salt)
        return self._write(
            "UPDATE users SET password_hash = ?, password_salt = ? WHERE email = ?", (digest, salt.hex(), email.strip().lower())
        ) > 0

    def delete_user(self, email: str) -> bool:
        return self._write("DELETE FROM users WHERE email = ?", (email.strip().lower(),)) > 0

    @staticmethod
    def _is_unique_violation(error: Exception) -> bool:
        if isinstance(error, sqlite3.IntegrityError):
            return True
        return getattr(error, "sqlstate", None) == "23505"


@lru_cache(maxsize=1)
def get_account_store() -> AccountStore:
    """Instancia unica, criada sob demanda (importar o modulo nao toca o banco)."""
    store = AccountStore()
    store.initialize()
    return store
