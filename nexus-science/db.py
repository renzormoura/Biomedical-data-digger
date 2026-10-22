"""Acesso a banco com o mesmo SQL em SQLite (desenvolvimento) e PostgreSQL (producao).

O SQL e escrito com `?` como marcador; para PostgreSQL ele e convertido em `%s`. So se usa
SQL portavel (`CREATE TABLE IF NOT EXISTS`, `INSERT ... ON CONFLICT`, chaves de texto).
Cada operacao usa uma conexao so sua: no SQLite abre e fecha; no PostgreSQL pega uma de um
pequeno conjunto de conexoes livres (nunca compartilhada entre threads ao mesmo tempo) e a
devolve no fim. Use `transaction()` para varias instrucoes atomicas.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from typing import Any

_DEFAULT_SQLITE_PATH = os.path.join(os.path.dirname(__file__), "accounts.sqlite3")
_IDLE_MAX = 4  # conexoes PostgreSQL guardadas para reuso
_STALE_AFTER = 20.0  # segundos parada antes de testar se ainda esta viva


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
        self._idle: list[tuple[Any, float]] = []  # conexoes PostgreSQL livres para reaproveitar (abrir uma nova, com TLS, custa centenas de ms)
        self._lock = threading.Lock()

    def _postgres_connection(self) -> Any:
        try:
            import psycopg
        except ImportError as error:
            raise DatabaseError("A dependencia psycopg nao esta instalada.") from error
        while True:
            with self._lock:
                item = self._idle.pop() if self._idle else None
            if item is None:
                return psycopg.connect(self.url, connect_timeout=15)
            connection, last_used = item
            if connection.closed:
                continue
            if time.monotonic() - last_used > _STALE_AFTER:  # parada ha um tempo: o servidor pode ter encerrado (o Neon suspende o banco ocioso)
                try:
                    connection.execute("SELECT 1")
                    connection.rollback()
                except Exception:  # noqa: BLE001 - qualquer falha aqui so significa "abra outra"
                    self._close(connection)
                    continue
            return connection

    @staticmethod
    def _close(connection: Any) -> None:
        with suppress(Exception):
            connection.close()

    def _release(self, connection: Any) -> None:
        if connection.closed or connection.info.transaction_status != 0:  # 0 = ociosa; qualquer outra coisa nao volta ao conjunto
            self._close(connection)
            return
        with self._lock:
            if len(self._idle) < _IDLE_MAX:
                self._idle.append((connection, time.monotonic()))
                return
        self._close(connection)

    @contextmanager
    def transaction(self) -> Iterator[Transaction]:
        """Conexao com commit no sucesso e rollback em qualquer excecao."""
        connection: Any
        if self.uses_postgres:
            connection = self._postgres_connection()
        else:
            connection = sqlite3.connect(self.sqlite_path, timeout=15)
            connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield Transaction(connection, self.uses_postgres)
            connection.commit()
        except BaseException:
            with suppress(Exception):  # conexao quebrada: sera descartada em _release
                connection.rollback()
            raise
        finally:
            if self.uses_postgres:
                self._release(connection)
            else:
                connection.close()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        with self.transaction() as tx:
            return tx.execute(sql, params)

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[tuple[Any, ...]]:
        with self.transaction() as tx:
            return tx.query(sql, params)
