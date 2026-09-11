"""Persistencia de contas com PostgreSQL em producao e SQLite localmente."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from dotenv import load_dotenv

load_dotenv()

_PASSWORD_ITERATIONS = 600_000
_DEFAULT_SQLITE_PATH = os.path.join(os.path.dirname(__file__), "accounts.sqlite3")


class AccountStoreError(RuntimeError):
    """Erro operacional do armazenamento de contas."""


class AccountStore:
    def __init__(self) -> None:
        self.database_url = os.environ.get("DATABASE_URL", "").strip()
        self.sqlite_path = os.environ.get("DATABASE_PATH", _DEFAULT_SQLITE_PATH)
        self.environment = os.environ.get("APP_ENV", "development").lower()
        if self.environment == "production" and not self.database_url:
            raise AccountStoreError(
                "DATABASE_URL e obrigatoria em producao. Configure um PostgreSQL persistente no Render."
            )
        self.uses_postgres = bool(self.database_url)

    @contextmanager
    def _connection(self) -> Iterator[object]:
        if self.uses_postgres:
            try:
                import psycopg
            except ImportError as error:
                raise AccountStoreError("A dependencia psycopg nao esta instalada.") from error

            database_url = self.database_url
            if database_url.startswith("postgres://"):
                database_url = "postgresql://" + database_url[len("postgres://"):]
            connection = psycopg.connect(database_url)
            try:
                yield connection
            finally:
                connection.close()
            return

        connection = sqlite3.connect(self.sqlite_path, timeout=15)
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connection() as connection:
            if self.uses_postgres:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS users (
                            email VARCHAR(320) PRIMARY KEY,
                            password_hash VARCHAR(128) NOT NULL,
                            password_salt VARCHAR(64) NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL
                        )
                        """
                    )
                connection.commit()
            else:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        email TEXT PRIMARY KEY,
                        password_hash TEXT NOT NULL,
                        password_salt TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                connection.commit()

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
        created_at = datetime.now(timezone.utc)

        try:
            with self._connection() as connection:
                if self.uses_postgres:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "INSERT INTO users (email, password_hash, password_salt, created_at) VALUES (%s, %s, %s, %s)",
                            (normalized_email, password_hash, salt.hex(), created_at),
                        )
                else:
                    connection.execute(
                        "INSERT INTO users (email, password_hash, password_salt, created_at) VALUES (?, ?, ?, ?)",
                        (normalized_email, password_hash, salt.hex(), created_at.isoformat()),
                    )
                connection.commit()
        except Exception as error:
            if self._is_unique_violation(error):
                return False
            raise AccountStoreError("Nao foi possivel salvar a conta.") from error
        return True

    def authenticate(self, email: str, password: str) -> bool:
        normalized_email = email.strip().lower()
        with self._connection() as connection:
            if self.uses_postgres:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT password_hash, password_salt FROM users WHERE email = %s",
                        (normalized_email,),
                    )
                    row = cursor.fetchone()
            else:
                row = connection.execute(
                    "SELECT password_hash, password_salt FROM users WHERE email = ?",
                    (normalized_email,),
                ).fetchone()

        if not row:
            return False
        stored_hash, stored_salt = row
        calculated_hash = self._password_digest(password, bytes.fromhex(stored_salt))
        return hmac.compare_digest(calculated_hash, stored_hash)

    @staticmethod
    def _is_unique_violation(error: Exception) -> bool:
        if isinstance(error, sqlite3.IntegrityError):
            return True
        return getattr(error, "sqlstate", None) == "23505"


account_store = AccountStore()
account_store.initialize()
