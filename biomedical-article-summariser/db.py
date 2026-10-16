"""Acesso a banco com o mesmo SQL em SQLite (desenvolvimento) e PostgreSQL (producao).

O SQL e escrito com `?` como marcador; para PostgreSQL ele e convertido em `%s`. So se usa
SQL portavel (`CREATE TABLE IF NOT EXISTS`, `INSERT ... ON CONFLICT`, chaves de texto).
Cada operacao abre e fecha sua conexao (ha pouca concorrencia e isso evita estado
compartilhado entre threads); use `transaction()` para varias instrucoes atomicas.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

_DEFAULT_SQLITE_PATH = os.path.join(os.path.dirname(__file__), "accounts.sqlite3")


class DatabaseError(RuntimeError):
    """Erro operacional do banco (mensagem segura, sem credenciais)."""


class Transaction:
    def __init__(self, connection: Any, postgres: bool) -> None:
        self._connection = connection
        self._postgres = postgres

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self._postgres else sql

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        """Executa uma instrucao e devolve o numero de linhas afetadas."""
        cursor = self._connection.cursor()
        try:
            cursor.execute(self._sql(sql), tuple(params))
            return int(cursor.rowcount)
        finally:
            cursor.close()

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[tuple[Any, ...]]:
        cursor = self._connection.cursor()
        try:
            cursor.execute(self._sql(sql), tuple(params))
            return [tuple(row) for row in cursor.fetchall()]
        finally:
            cursor.close()


class Database:
    def __init__(self, database_url: str | None = None, sqlite_path: str | None = None) -> None:
        url = os.environ.get("DATABASE_URL", "") if database_url is None else database_url
        self.url = url.strip()
        if self.url.startswith("postgres://"):
            self.url = "postgresql://" + self.url[len("postgres://"):]
        self.sqlite_path = sqlite_path or os.environ.get("DATABASE_PATH", _DEFAULT_SQLITE_PATH)
        self.uses_postgres = bool(self.url)

    @contextmanager
    def transaction(self) -> Iterator[Transaction]:
        """Conexao com commit no sucesso e rollback em qualquer excecao."""
        connection: Any
        if self.uses_postgres:
            try:
                import psycopg
            except ImportError as error:
                raise DatabaseError("A dependencia psycopg nao esta instalada.") from error
            connection = psycopg.connect(self.url)
        else:
            connection = sqlite3.connect(self.sqlite_path, timeout=15)
            connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield Transaction(connection, self.uses_postgres)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        with self.transaction() as tx:
            return tx.execute(sql, params)

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[tuple[Any, ...]]:
        with self.transaction() as tx:
            return tx.query(sql, params)
