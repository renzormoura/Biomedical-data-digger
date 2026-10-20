"""Teste de contrato da API: percorre TODAS as rotas e compara com um retrato salvo (`tests/golden/api_contract.json`).

Serve de rede de seguranca para refatoracoes: se qualquer rota mudar de status, de campos ou de valores, o teste falha
e mostra o que mudou. Tudo e deterministico: fontes simuladas, sem rede, sem IA real. Datas, horas e identificadores
aleatorios sao substituidos por marcadores antes de comparar.

Para registrar um retrato novo de proposito (mudanca de comportamento aprovada):  UPDATE_GOLDEN=1 pytest tests/test_api_contract.py
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import downloads
import enrichment
import pages
from account_store import AccountStore
from account_tokens import AccountTokens
from alerts import AlertService, AlertStore
from config import Settings
from db import Database
from discovery import DiscoveryService
from feed import FeedItem, FeedService, FeedStore, SourceState
from feed_sources import SOURCES
from library_store import LibraryStore
from notifications import NotificationService, NotificationStore
from profiles import ProfileStore
from ratelimit import SlidingWindowLimiter
from reports import ReportStore
from test_discovery import FakeCatalog, make_work
from test_web import FakeGenerator
from usage import UsageLog
from web import create_app
from workflow import AnalysisService, ArticleRepository

GOLDEN = Path(__file__).parent / "golden" / "api_contract.json"
PASSWORD = "senha-forte-123"
EMAIL = "contrato@exemplo.com"
TODAY = date.today().isoformat()

_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATE_BR = re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b")
_HEX_ID = re.compile(r"\b[0-9a-f]{32}\b")
_TOKEN_IN_PATH = re.compile(r"(/lista/)[\w-]{8,}")
_ASSET_VERSION = re.compile(r"\?v=[0-9a-f]+")  # hash dos arquivos estaticos: muda a cada alteracao de JS/CSS


def _norm_text(text: str) -> str:
    text = _ASSET_VERSION.sub("?v=<hash>", text)
    text = _TIMESTAMP.sub("<ts>", text)
    text = _HEX_ID.sub("<id>", text)
    text = _TOKEN_IN_PATH.sub(r"\1<token>", text)
    text = _DATE.sub("<date>", text)
    return _DATE_BR.sub("<date>", text)


def normalize(value: Any, key: str = "") -> Any:
    if isinstance(value, dict):
        return {k: normalize(v, k) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [normalize(v, key) for v in value]
    if isinstance(value, str):
        return "<token>" if key == "token" else _norm_text(value)
    if key == "since" and isinstance(value, int):  # epoch de inicio do registro de uso
        return "<epoch>"
    return value


ABSTRACT = (
    "Background: Metformin is widely used. Methods: We pooled 14 trials (n=18,450). "
    "Results: Lower risk (RR 0.89; 95% CI 0.81-0.98; p=0.02). Conclusions: A modest reduction. Registered NCT01234567."
)


class Inbox:
    """E-mail de teste: guarda as mensagens para o roteiro pegar os tokens dos links."""

    def __init__(self) -> None:
        self.sent: list[Any] = []

    def send(self, message: Any) -> None:
        self.sent.append(message)

    def token(self) -> str:
        return re.search(r"token=([\w%-]+)", self.sent[-1].text).group(1)  # type: ignore[union-attr]


class Recorder:
    """Faz as chamadas e guarda (rota, status, corpo normalizado) na ordem em que aconteceram."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.entries: dict[str, Any] = {}
        self.covered: set[tuple[str, str]] = set()

    def call(self, method: str, template: str, path: str | None = None, *, label: str = "", **kwargs: Any) -> Any:
        response = self.client.request(method, path or template, **kwargs)
        self.covered.add((method, template))
        key = f"{method} {template}" + (f" [{label}]" if label else "")
        assert key not in self.entries, f"chamada repetida sem rotulo: {key}"
        content_type = response.headers.get("content-type", "")
        entry: dict[str, Any] = {"status": response.status_code, "type": content_type.split(";")[0]}
        if "json" in content_type:
            entry["json"] = normalize(response.json())
        elif content_type.startswith(("text/", "application/xml")):
            entry["text"] = _norm_text(response.text)[:600]
        else:
            entry["bytes"] = bool(response.content)
        disposition = response.headers.get("content-disposition")
        if disposition:
            entry["disposition"] = _norm_text(disposition)
        self.entries[key] = entry
        return response


@pytest.fixture
def recorder(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "contract.sqlite3"))
    monkeypatch.setenv("APP_ENV", "development")
    # nada de rede: ensaios, citacoes, dados relacionados e texto completo respondem "sem dados"
    monkeypatch.setattr(enrichment, "fetch_trial", lambda nct: None)
    monkeypatch.setattr(enrichment, "fetch_citations", lambda doi: 7)
    monkeypatch.setattr(enrichment, "fetch_related_data", lambda doi: ())
    monkeypatch.setattr(downloads, "fetch_fulltext_xml", lambda pmcid: None)
    monkeypatch.setattr(DiscoveryService, "_pmcid_from_europepmc", lambda self, work: "")

    accounts = AccountStore()
    accounts.initialize()
    database = Database(database_url="", sqlite_path=str(tmp_path / "contract.sqlite3"))
    library, reports, alert_store = LibraryStore(database), ReportStore(database), AlertStore(database)
    profiles, notification_store, feed_store = ProfileStore(database), NotificationStore(database), FeedStore(database)
    account_tokens = AccountTokens(database)
    for store in (library, reports, alert_store, profiles, notification_store, feed_store, account_tokens):
        store.initialize()
    inbox = Inbox()

    works = [make_work(str(n), title=f"Estudo de contrato {n}", abstract=ABSTRACT, year=2024) for n in (1, 2, 3)]
    catalogs = [FakeCatalog(works=works), FakeCatalog(id="pubmed", name="PubMed (MEDLINE)", works=works[:2])]
    for catalog in catalogs:
        catalog.combined = True
    discovery = DiscoveryService(catalogs, SlidingWindowLimiter(1000, 60), fallback=None)

    def search_for_alerts(query, user):
        return [make_work("9", title="Artigo novo sobre pediatria", abstract=ABSTRACT, year=date.today().year,
                          published=TODAY)]

    alerts = AlertService(alert_store, search_for_alerts)
    from brasil import anvisa, conitec, rename

    notifications = NotificationService(
        notification_store, fetch_work=lambda ref: make_work(ref, abstract=ABSTRACT), library=library, reports=reports,
        bases=lambda: (anvisa.carregar(), conitec.carregar(), rename.carregar()),
    )
    feed_service = FeedService(feed_store, fetcher=lambda url, etag, modified: (_ for _ in ()).throw(AssertionError("sem rede")))
    now = date.today().isoformat() + "T12:00:00+00:00"
    feed_store.upsert(
        [FeedItem("a" * 24, SOURCES[0].id, "https://exemplo.com/a", "Vacinas em pediatria", "Resumo curto.", now, True, ("medicina/pediatria",), ("medicina",))],
        now,
    )
    for source in SOURCES:
        feed_store.set_state(SourceState(source.id, now, now, "", 0))

    repository = ArticleRepository(lambda raw: ("Metformina e desfechos", ABSTRACT, "Fonte"))
    service = AnalysisService(repository, FakeGenerator(), SlidingWindowLimiter(1000, 60))
    settings = Settings(session_secret="k" * 40, login_attempts_per_minute=1000, alerts_cron_token="t" * 30, admin_token="a" * 30)
    app = create_app(
        service, repository, settings, account_store_factory=lambda: accounts, search_fn=lambda query, limit, area: [{
            "title": "T 1", "journal": "J", "year": 2024, "pmid": "1", "source": "MED", "url": "https://x/1", "doi": "10.1/x",
            "reliability": "Alta", "reliability_score": 0.95}],
        usage_log=UsageLog(), discovery=discovery, library=library, alerts=alerts, reports=reports, profiles=profiles,
        notifications=notifications, feed=feed_service, account_tokens=account_tokens, mailer=inbox,
    )
    recorder = Recorder(TestClient(app, base_url="http://testserver"))
    recorder.app = app  # type: ignore[attr-defined]
    recorder.inbox = inbox  # type: ignore[attr-defined]
    return recorder


def run_scenario(r: Recorder) -> None:  # noqa: C901 - e um roteiro linear de proposito
    c = r.call
    # paginas e saude
    c("GET", "/")
    c("GET", "/ia")
    c("GET", "/healthz")
    # visitante
    c("GET", "/api/auth/me", label="visitante")
    c("GET", "/api/discover/options")
    c("GET", "/api/discover/search", params={"q": "metformina", "per_page": 5})
    c("GET", "/api/discover/search", label="uma fonte", params={"q": "metformina", "source": "pubmed", "sort": "cited"})
    c("GET", "/api/discover/panorama", params={"q": "metformina"})
    c("GET", "/api/discover/work", params={"ref": "1"})
    c("GET", "/api/discover/brief", params={"ref": "1"})
    c("GET", "/api/discover/similar", params={"ref": "1"})
    c("GET", "/api/discover/enrichment", params={"ref": "1"})
    c("GET", "/api/discover/cite", params={"ref": "1", "format": "ris"})
    c("GET", "/api/discover/downloads", params={"ref": "1"})
    for kind, fmt in (("abstract", "md"), ("sheet", "txt"), ("citation", "bibtex"), ("fulltext", "txt")):
        c("GET", "/api/discover/download", label=f"{kind}-{fmt}", params={"ref": "1", "kind": kind, "format": fmt})
    c("GET", "/api/discover/brasil", params={"ref": "1"})
    c("GET", "/api/brasil/conitec", params={"q": "metformina"})
    c("GET", "/api/brasil/medicamento", params={"q": "metformina"})
    c("GET", "/api/profile/options")
    c("GET", "/api/interests/options")
    c("GET", "/api/feed", params={"mode": "tudo"})
    c("GET", "/api/feed/sources")
    c("GET", "/api/library", label="sem conta")
    c("GET", "/api/shared/{token}", "/api/shared/inexistente", label="inexistente")
    # Laboratorio de IA
    base = {"article_id": "33984217", "model": pages.DEFAULT_MODEL}
    c("POST", "/api/analyze", json={"page": "geral", "button": "sumario", **base})
    c("POST", "/api/extract", json={"page": "geral", "button": "extrair-do-artigo", "article_id": "33984217"})
    c("POST", "/api/cite", json={"article_id": "33984217", "style": "ABNT"})
    c("POST", "/api/audit", json={**base, "previous": "Mortalidade caiu de 12,5% para 8,1%."})
    c("POST", "/api/compare", json={"article_a": "33984217", "article_b": "33984218", "analysis": "Eficácia", "model": pages.DEFAULT_MODEL})
    c("POST", "/api/search", json={"query": "metformina", "area": "Todas", "limit": 3})
    c("POST", "/api/export/analysis", json={"title": "T", "label": "Sumário", "markdown": "## Título\n\n- item", "format": "md"})
    c("GET", "/api/admin/usage", label="sem token")
    c("GET", "/api/admin/usage", label="com token", headers={"Authorization": "Bearer " + "a" * 30})
    # conta
    c("POST", "/api/auth/register", json={"email": EMAIL, "password": PASSWORD})
    c("POST", "/api/auth/logout")
    c("POST", "/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    c("GET", "/api/auth/me", label="logado")
    # confirmacao de e-mail e recuperacao de senha (a conta ja recebeu o link de confirmacao ao se cadastrar)
    c("POST", "/api/account/resend-verification", label="no intervalo")
    c("POST", "/api/auth/verify", json={"token": "invalido"}, label="invalido")
    c("POST", "/api/auth/verify", json={"token": r.inbox.token()}, label="valido")  # type: ignore[attr-defined]
    c("POST", "/api/account/resend-verification", label="ja confirmado")
    c("POST", "/api/auth/forgot", json={"email": "ninguem@exemplo.com"}, label="desconhecido")
    c("POST", "/api/auth/forgot", json={"email": EMAIL}, label="conhecido")
    c("POST", "/api/auth/reset", json={"token": "invalido", "password": "outra-senha-forte-789"}, label="invalido")
    c("GET", "/api/account")
    c("GET", "/api/profile", label="inicial")
    c("PUT", "/api/profile", json={"profile": "saude"})
    c("GET", "/api/interests", label="inicial")
    c("PUT", "/api/interests", json={"topics": [{"area": "medicina", "subtopics": []}], "languages": ["pt"], "terms": ["metformina"]})
    # biblioteca e listas
    c("POST", "/api/library", json={"ref": "1"})
    c("POST", "/api/library", label="segundo", json={"ref": "2"})
    c("PUT", "/api/library/tags", json={"ref": "1", "tags": ["diabetes"]})
    c("GET", "/api/library")
    for fmt in ("bibtex", "ris", "csv", "json"):
        c("GET", "/api/library/export", label=fmt, params={"format": fmt})
    created = c("POST", "/api/lists", json={"name": "Minha lista"}).json()
    list_id = created["id"]
    c("POST", "/api/lists/{list_id}/items", f"/api/lists/{list_id}/items", label="1", json={"ref": "1"})
    c("POST", "/api/lists/{list_id}/items", f"/api/lists/{list_id}/items", label="2", json={"ref": "2"})
    c("GET", "/api/lists")
    token = c("POST", "/api/lists/{list_id}/share", f"/api/lists/{list_id}/share").json()["token"]
    c("GET", "/api/shared/{token}", f"/api/shared/{token}", label="compartilhada")
    c("DELETE", "/api/lists/{list_id}/items", f"/api/lists/{list_id}/items", params={"ref": "2"})
    c("DELETE", "/api/lists/{list_id}/share", f"/api/lists/{list_id}/share")
    # relatorios
    report_id = c("POST", "/api/reports", json={"list_id": list_id, "title": "Relatório", "question": "Metformina?"}).json()["id"]
    rp = f"/api/reports/{report_id}"
    c("GET", "/api/reports")
    c("GET", "/api/reports/{report_id}", rp)
    c("PUT", "/api/reports/{report_id}", rp, json={"title": "Relatório 2", "question": "Metformina?", "methodNote": "nota",
                                                    "items": [{"ref": "1", "included": True, "note": "ok"}], "substances": ["metformina"]})
    c("GET", "/api/reports/{report_id}/history", rp + "/history")
    c("POST", "/api/reports/{report_id}/search", rp + "/search", json={"query": "metformina"})
    c("POST", "/api/reports/{report_id}/add", rp + "/add", json={"refs": ["2"], "origin": "lista"})
    c("POST", "/api/reports/{report_id}/restore", rp + "/restore", json={"version": 1})
    c("GET", "/api/reports/{report_id}/brasil", rp + "/brasil")
    for fmt in ("html", "md", "txt", "docx"):
        c("GET", "/api/reports/{report_id}/download", rp + "/download", label=fmt, params={"format": fmt})
    # analises salvas
    saved = c("POST", "/api/analyses", json={"article_id": "1", "page": "geral", "label": "Sumário", "markdown": "## T\n\ntexto"}).json()
    analysis_id = saved.get("id", "inexistente")
    c("GET", "/api/analyses", params={"ref": "1"})
    c("GET", "/api/analyses/{analysis_id}", f"/api/analyses/{analysis_id}")
    c("GET", "/api/analyses/{analysis_id}/download", f"/api/analyses/{analysis_id}/download", params={"format": "md"})
    c("DELETE", "/api/analyses/{analysis_id}", f"/api/analyses/{analysis_id}")
    # avisos e notificacoes
    c("POST", "/api/alerts/check", json={"force": True}, label="primeira")
    c("POST", "/api/alerts/check", json={"force": True}, label="segunda")
    box = c("GET", "/api/alerts").json()
    first = (box.get("alerts") or [{"id": "x"}])[0]["id"]
    c("POST", "/api/alerts/read", json={"id": first}, label="um")
    c("POST", "/api/alerts/read", json={}, label="todos")
    c("DELETE", "/api/alerts", params={"id": first})
    c("GET", "/api/notifications/prefs")
    c("PUT", "/api/notifications/prefs", json={"kinds": {"retratacao": False}})
    # rotina agendada
    c("POST", "/api/internal/alerts/run", label="sem token")
    c("POST", "/api/internal/alerts/run", label="com token", headers={"Authorization": "Bearer " + "t" * 30})
    # remocoes
    c("DELETE", "/api/library", params={"ref": "2"})
    c("DELETE", "/api/reports/{report_id}", rp)
    c("DELETE", "/api/lists/{list_id}", f"/api/lists/{list_id}")
    # conta: senha, copia e exclusao
    c("POST", "/api/account/password", json={"current": PASSWORD, "new": "nova-senha-forte-456"})
    c("GET", "/api/account/export")
    c("DELETE", "/api/account", json={"password": "nova-senha-forte-456"})
    c("GET", "/api/auth/me", label="apos exclusao")


def api_routes(app: Any) -> set[tuple[str, str]]:
    found = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/api/") or path in ("/", "/ia", "/healthz"):
            for method in getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}:
                found.add((method, path))
    return found


def test_api_contract_matches_the_golden_snapshot(recorder):
    run_scenario(recorder)
    missing = api_routes(recorder.app) - recorder.covered
    assert not missing, f"rotas sem cobertura no teste de contrato: {sorted(missing)}"
    current = json.dumps(recorder.entries, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if os.environ.get("UPDATE_GOLDEN") == "1" or not GOLDEN.exists():
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(current, encoding="utf-8")
        pytest.skip("retrato gravado; rode de novo para comparar")
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    actual = json.loads(current)
    diffs = [f"{key}: esperado {expected.get(key)!r} / obtido {actual.get(key)!r}"
             for key in sorted(set(expected) | set(actual)) if expected.get(key) != actual.get(key)]
    assert not diffs, "o contrato da API mudou:\n" + "\n".join(d[:700] for d in diffs[:8])
