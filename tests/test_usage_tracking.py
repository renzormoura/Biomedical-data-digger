"""Fase 0: captura de uso nos backends, registro no servico e relatorio administrativo."""

import sys
import types
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import pages
from config import Settings
from domain import Completion, NexusError
from llm_service import GroqBackend, LLMRouter, OllamaBackend
from prompt_builders import build_message_sumario
from ratelimit import SlidingWindowLimiter
from test_llm_backends import MSGS, fake_groq_module
from test_web import FakeGenerator as WebFakeGenerator
from test_web import analyze_payload
from test_workflow import CountingResolver, FakeGenerator
from usage import UsageLog
from web import create_app
from workflow import AnalysisService, ArticleRepository


# ------------------------------------------------------------------ backends
def test_groq_complete_reports_provider_usage(monkeypatch):
    module, client = fake_groq_module()
    original = client.chat.completions.create.side_effect

    def with_usage(**kw):
        response = original(**kw)
        response.usage = types.SimpleNamespace(prompt_tokens=321, completion_tokens=45)
        return response

    client.chat.completions.create.side_effect = with_usage
    monkeypatch.setitem(sys.modules, "groq", module)
    result = GroqBackend("key").complete(MSGS, "GPT-OSS 20B (Groq)")
    assert (result.text, result.prompt_tokens, result.completion_tokens, result.total_tokens) == ("resposta", 321, 45, 366)


def test_groq_complete_without_usage_leaves_tokens_unknown(monkeypatch):
    module, _ = fake_groq_module()
    monkeypatch.setitem(sys.modules, "groq", module)
    result = GroqBackend("key").complete(MSGS, "GPT-OSS 20B (Groq)")
    assert result.prompt_tokens is None and result.total_tokens is None


def test_ollama_complete_reads_eval_counts(monkeypatch):
    fake = types.ModuleType("ollama")
    fake.pull = MagicMock()
    fake.chat = MagicMock(return_value={"message": {"content": "ok"}, "prompt_eval_count": 90, "eval_count": 12})
    monkeypatch.setitem(sys.modules, "ollama", fake)
    result = OllamaBackend().complete(MSGS, "Llama (local)")
    assert (result.prompt_tokens, result.completion_tokens) == (90, 12)


def test_router_complete_delegates_and_generate_returns_text(monkeypatch):
    module, _ = fake_groq_module()
    monkeypatch.setitem(sys.modules, "groq", module)
    router = LLMRouter([GroqBackend("k")])
    assert router.complete(MSGS, "GPT-OSS 20B (Groq)").text == router.generate(MSGS, "GPT-OSS 20B (Groq)") == "resposta"


def test_completion_total_tokens():
    assert Completion("x").total_tokens is None
    assert Completion("x", 10, None).total_tokens == 10
    assert Completion("x", 10, 5).total_tokens == 15


# ------------------------------------------------------------------ servico
def _service_with_log(gen):
    log = UsageLog()
    service = AnalysisService(ArticleRepository(CountingResolver()), gen, SlidingWindowLimiter(100, 60), usage_log=log)
    return service, log


def test_usage_is_recorded_from_provider_numbers_per_button():
    service, log = _service_with_log(FakeGenerator(usage=(1300, 420)))
    service.analyze("33984217", "m", build_message_sumario, "Sumário", usage_key="geral/sumario", client_id="u:a@b.com")
    stats = log.snapshot()["by_key"]["geral/sumario"]
    assert stats["prompt_tokens"] == 1300 and stats["completion_tokens"] == 420 and stats["estimated_calls"] == 0


def test_usage_falls_back_to_estimate_when_provider_gives_none():
    service, log = _service_with_log(FakeGenerator("resposta com texto"))
    service.analyze("33984217", "m", build_message_sumario, "Sumário")
    stats = log.snapshot()["by_key"]["Sumário"]  # sem usage_key, usa o rotulo
    assert stats["estimated_calls"] == 1 and stats["prompt_tokens"] > 500 and stats["completion_tokens"] > 0


def test_audit_and_compare_are_recorded_under_their_own_keys():
    service, log = _service_with_log(FakeGenerator(usage=(100, 50)))
    service.audit("33984217", "m", "resposta")
    service.compare("33984217", "33984218", "Eficácia", "m", usage_key="medicina/compare")
    assert set(log.snapshot()["by_key"]) == {"audit", "medicina/compare"}


def test_failed_generation_is_not_recorded():
    class Boom(FakeGenerator):
        def complete(self, messages, model, options=None):
            raise RuntimeError("503")

    service, log = _service_with_log(Boom())
    with pytest.raises(NexusError):
        service.analyze("33984217", "m", build_message_sumario, "S")
    assert log.snapshot()["totals"]["calls"] == 0


def test_service_works_without_usage_log():
    service = AnalysisService(ArticleRepository(CountingResolver()), FakeGenerator(), SlidingWindowLimiter(5, 60))
    assert "Sumário" in service.analyze("33984217", "m", build_message_sumario, "Sumário")


# ------------------------------------------------------------------ relatorio admin
@pytest.fixture
def admin(tmp_path, monkeypatch):
    from account_store import AccountStore

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "a.sqlite3"))
    store = AccountStore()
    store.initialize()
    repository = ArticleRepository(lambda raw: ("Titulo", "Em 1200 pacientes a mortalidade caiu de 12,5% para 8,1%.", "F"))

    def build(token="t" * 30, attempts=50):
        log = UsageLog()
        service = AnalysisService(repository, WebFakeGenerator(), SlidingWindowLimiter(50, 60), usage_log=log)
        settings = Settings(session_secret="k" * 40, admin_token=token, login_attempts_per_minute=attempts)
        app = create_app(service, repository, settings, account_store_factory=lambda: store,
                         search_fn=lambda *a, **k: [], usage_log=log)
        return TestClient(app), token

    return build


def test_admin_usage_is_disabled_without_token(admin):
    client, _ = admin(token="")
    assert client.get("/api/admin/usage").status_code == 404


def test_admin_usage_requires_bearer_token_and_reports_per_button(admin):
    client, token = admin()
    client.post("/api/analyze", json=analyze_payload())
    assert client.get("/api/admin/usage").status_code == 401
    assert client.get("/api/admin/usage", headers={"authorization": "Bearer errado"}).status_code == 401
    report = client.get("/api/admin/usage", headers={"authorization": f"Bearer {token}"}).json()
    assert report["by_key"]["geral/sumario"]["prompt_tokens"] == 120
    assert report["totals"]["total_tokens"] == 200


def test_admin_usage_attempts_are_rate_limited(admin):
    client, _ = admin(attempts=2)
    codes = [client.get("/api/admin/usage", headers={"authorization": "Bearer x"}).status_code for _ in range(3)]
    assert codes == [401, 401, 429]


def test_audit_and_compare_use_page_in_usage_key(admin):
    client, token = admin()
    client.post("/api/audit", json={"article_id": "1234567", "model": pages.DEFAULT_MODEL, "previous": "x", "page": "medicina"})
    client.post("/api/compare", json={"article_a": "1234567", "article_b": "7654321", "analysis": "Eficácia",
                                      "model": pages.DEFAULT_MODEL, "page": "geral"})
    keys = set(client.get("/api/admin/usage", headers={"authorization": f"Bearer {token}"}).json()["by_key"])
    assert keys == {"medicina/audit", "geral/compare"}


def test_admin_token_must_be_strong_or_empty(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "curto")
    with pytest.raises(ValueError, match="ADMIN_TOKEN"):
        Settings.from_env()
    monkeypatch.setenv("ADMIN_TOKEN", "x" * 24)
    settings = Settings.from_env()
    assert settings.admin_token and "xxxx" not in repr(settings)
    monkeypatch.delenv("ADMIN_TOKEN")
    assert Settings.from_env().admin_token == ""
