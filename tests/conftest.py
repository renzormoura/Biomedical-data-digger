"""Configuracao compartilhada: coloca o codigo-fonte no path e isola a rede."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "biomedical-article-summariser"))


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch):
    """Testes nunca fazem DNS real: todo host resolve para um IP publico fixo."""
    import security

    monkeypatch.setattr(security, "_resolve_host", lambda host: ["93.184.216.34"])


def make_response(content: bytes = b"", status: int = 200, headers: dict | None = None):
    """Response real do `requests`, com corpo em memoria (compativel com safe_get)."""
    import requests

    response = requests.Response()
    response.status_code = status
    response._content = content
    response._content_consumed = True
    response.headers.update(headers or {})
    return response


@pytest.fixture(autouse=True)
def _postgres_schema(monkeypatch, request):
    """Roda a suite contra PostgreSQL de verdade quando `TEST_POSTGRES_URL` esta definida.

    Cada teste ganha um schema proprio (isolamento total) e todo `Database(database_url="")` -- que nos testes
    significa "o banco local" -- passa a apontar para ele. Sem a variavel, nada muda e os testes usam SQLite.
    Uso:  TEST_POSTGRES_URL=postgresql://usuario:senha@localhost:55432/bdd pytest
    """
    base = os.environ.get("TEST_POSTGRES_URL", "").strip()
    if not base:
        yield
        return
    if request.node.get_closest_marker("sqlite_only"):
        pytest.skip("comportamento especifico do SQLite; nao se aplica ao PostgreSQL")
    import uuid

    import psycopg

    import db

    schema = f"t_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(base, autocommit=True) as admin:
        admin.execute(f'CREATE SCHEMA "{schema}"')
    url = f"{base}{'&' if '?' in base else '?'}options=-csearch_path%3D{schema}"
    original = db.Database.__init__

    def init(self, database_url=None, sqlite_path=None):
        original(self, url if database_url == "" else database_url, sqlite_path)

    monkeypatch.setattr(db.Database, "__init__", init)
    monkeypatch.setenv("DATABASE_URL", url)

    import account_store

    account_store.get_account_store.cache_clear()  # a instancia unica nao pode apontar para o schema de outro teste
    try:
        yield
    finally:
        monkeypatch.undo()
        account_store.get_account_store.cache_clear()
        with psycopg.connect(base, autocommit=True) as admin:
            admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
