"""Termos de Uso e Politica de Privacidade: textos servidos, aceite no cadastro, registro da versao aceita e exigencias de producao."""

import re
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import legal
from account_consent import ConsentStore
from account_store import AccountStore
from config import ConfigurationError, Settings
from db import Database
from library_store import LibraryStore
from ratelimit import SlidingWindowLimiter
from web import create_app
from workflow import AnalysisService, ArticleRepository

EMAIL = "ana@exemplo.com"
PASSWORD = "senha-forte-123"


def build(tmp_path, monkeypatch, **settings_kwargs):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "a.sqlite3"))
    accounts = AccountStore()
    accounts.initialize()
    database = Database(database_url="", sqlite_path=str(tmp_path / "a.sqlite3"))
    consent = ConsentStore(database)
    consent.initialize()
    library = LibraryStore(database)
    library.initialize()
    repository = ArticleRepository(lambda raw: ("T", "Resumo suficiente para o teste.", "s"))
    service = AnalysisService(repository, MagicMock(), SlidingWindowLimiter(50, 60))
    settings = Settings(session_secret="k" * 40, login_attempts_per_minute=1000, **settings_kwargs)
    app = create_app(service, repository, settings, account_store_factory=lambda: accounts, search_fn=lambda *a, **k: [],
                     library=library, consent=consent)
    return TestClient(app, base_url="http://testserver"), consent


CONFIGURED = {"legal_controller": "Empresa Exemplo Ltda.", "legal_contact": "privacidade@exemplo.com", "legal_forum": "São Paulo/SP"}


def test_documents_are_served_with_version_and_the_controller_data(tmp_path, monkeypatch):
    client, _ = build(tmp_path, monkeypatch, **CONFIGURED)
    for doc, title in (("termos", "Termos de Uso"), ("privacidade", "Política de Privacidade")):
        body = client.get(f"/api/legal/{doc}").json()
        assert body["title"] == title and body["version"] == legal.VERSION
        assert "Empresa Exemplo Ltda." in body["html"] and "privacidade@exemplo.com" in body["html"]
        assert "{{" not in body["html"] and "[a definir]" not in body["html"]


def test_missing_controller_data_shows_a_visible_placeholder_and_the_internal_link_works(tmp_path, monkeypatch):
    client, _ = build(tmp_path, monkeypatch)
    html = client.get("/api/legal/termos").json()["html"]
    assert "[a definir]" in html
    assert '<a href="/#/privacidade">Política de Privacidade</a>' in html  # link interno permitido


def test_unknown_document_is_404_and_the_html_is_escaped(tmp_path, monkeypatch):
    client, _ = build(tmp_path, monkeypatch, legal_controller="<script>alert(1)</script>", legal_contact="x@y.z")
    assert client.get("/api/legal/outro").status_code == 404
    html = client.get("/api/legal/termos").json()["html"]
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_every_placeholder_in_the_texts_is_known():
    known = set(legal.values(Settings()))
    for _, filename in legal.DOCS.values():
        used = set(re.findall(r"\{\{(\w+)\}\}", (legal.TEXTS_DIR / filename).read_text(encoding="utf-8")))
        assert used <= known, used - known


def test_registration_requires_the_acceptance_when_configured_and_records_the_version(tmp_path, monkeypatch):
    client, consent = build(tmp_path, monkeypatch, require_terms=True, **CONFIGURED)
    refused = client.post("/api/auth/register", json={"email": EMAIL, "password": PASSWORD})
    assert refused.status_code == 400 and "Termos de Uso" in refused.json()["error"]
    assert client.post("/api/auth/register", json={"email": EMAIL, "password": PASSWORD, "acceptTerms": False}).status_code == 400
    assert client.post("/api/auth/register", json={"email": EMAIL, "password": PASSWORD, "acceptTerms": True}).status_code == 200
    version, accepted_at = consent.get(EMAIL)
    assert version == legal.VERSION and accepted_at.endswith("+00:00")
    exported = client.get("/api/account/export").json()["account"]["terms"]
    assert exported["version"] == legal.VERSION


def test_without_the_requirement_registration_works_and_records_only_an_explicit_acceptance(tmp_path, monkeypatch):
    client, consent = build(tmp_path, monkeypatch)
    assert client.post("/api/auth/register", json={"email": EMAIL, "password": PASSWORD}).status_code == 200
    assert consent.get(EMAIL) is None
    assert client.get("/api/account/export").json()["account"]["terms"] is None


def test_deleting_the_account_removes_the_acceptance(tmp_path, monkeypatch):
    client, consent = build(tmp_path, monkeypatch, require_terms=True, **CONFIGURED)
    client.post("/api/auth/register", json={"email": EMAIL, "password": PASSWORD, "acceptTerms": True})
    assert client.request("DELETE", "/api/account", json={"password": PASSWORD}).status_code == 200
    assert consent.get(EMAIL) is None


def test_production_requires_the_controller_identification(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SESSION_SECRET", "s" * 40)
    for name in ("LEGAL_CONTROLLER", "LEGAL_CONTACT", "REQUIRE_TERMS", "SMTP_HOST"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ConfigurationError, match="LEGAL_CONTROLLER"):
        Settings.from_env()
    monkeypatch.setenv("REQUIRE_TERMS", "0")
    assert Settings.from_env().require_terms is False
    monkeypatch.setenv("REQUIRE_TERMS", "1")
    monkeypatch.setenv("LEGAL_CONTROLLER", "Empresa Exemplo")
    monkeypatch.setenv("LEGAL_CONTACT", "privacidade@exemplo.com")
    settings = Settings.from_env()
    assert settings.require_terms and settings.legal_controller == "Empresa Exemplo"


def test_development_does_not_require_terms_by_default(monkeypatch):
    for name in ("APP_ENV", "REQUIRE_TERMS", "LEGAL_CONTROLLER", "LEGAL_CONTACT"):
        monkeypatch.delenv(name, raising=False)
    assert Settings.from_env().require_terms is False
