"""Falhas do provedor de LLM viram mensagens seguras: nada de IDs internos para o usuario."""

import pytest
from fastapi.testclient import TestClient

from config import Settings
from domain import DiggerError, RateLimitedError
from prompt_builders import build_message_sumario
from ratelimit import SlidingWindowLimiter
from test_web import FakeGenerator as WebFakeGenerator
from test_web import analyze_payload
from test_workflow import FakeGenerator
from web import create_app
from workflow import PROVIDER_RATE_LIMIT_MESSAGE, AnalysisService, ArticleRepository

RAW_429 = (
    "Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-20b` in organization "
    "`org_01m1d4rm2hespbxsge1snpakvg` on tokens per day (TPD): Limit 200000, Used 197645'}}"
)


class ProviderError(Exception):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code


def failing(error):
    class Failing(FakeGenerator):
        def complete(self, messages, model, options=None):
            raise error

    return Failing()


def service(generator):
    return AnalysisService(ArticleRepository(lambda raw: ("T", "Em 1200 pacientes a mortalidade caiu.", "s")),
                           generator, SlidingWindowLimiter(100, 60))


def test_provider_429_becomes_a_friendly_rate_limit_error_without_internal_ids():
    with pytest.raises(RateLimitedError) as info:
        service(failing(ProviderError(429, RAW_429))).analyze("33984217", "m", build_message_sumario, "S")
    message = info.value.user_message
    assert message == PROVIDER_RATE_LIMIT_MESSAGE
    assert "org_" not in message and "197645" not in message and "gpt-oss" not in message


def test_other_provider_http_errors_show_only_the_status_code():
    with pytest.raises(DiggerError) as info:
        service(failing(ProviderError(503, "upstream said: secret-internal-detail req_abc123"))).analyze(
            "33984217", "m", build_message_sumario, "S"
        )
    assert "HTTP 503" in info.value.user_message
    assert "secret-internal-detail" not in info.value.user_message and "req_abc123" not in info.value.user_message


def test_errors_without_status_keep_the_previous_behavior():
    with pytest.raises(DiggerError, match="503 upstream"):
        service(failing(RuntimeError("503 upstream"))).analyze("33984217", "m", build_message_sumario, "S")


def test_provider_error_is_never_cached_and_next_call_recovers():
    class Recovering(FakeGenerator):
        def complete(self, messages, model, options=None):
            self.calls.append(1)
            if len(self.calls) == 1:
                raise ProviderError(429, RAW_429)
            return super().complete(messages, model, options)

    gen = Recovering()
    svc = service(gen)
    with pytest.raises(RateLimitedError):
        svc.analyze("33984217", "m", build_message_sumario, "S")
    assert "Mortalidade" in svc.analyze("33984217", "m", build_message_sumario, "S")


def test_api_returns_429_with_the_friendly_message(tmp_path, monkeypatch):
    from account_store import AccountStore

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "a.sqlite3"))
    store = AccountStore()
    store.initialize()
    repository = ArticleRepository(lambda raw: ("T", "Em 1200 pacientes a mortalidade caiu.", "s"))
    generator = WebFakeGenerator()
    generator.complete = lambda *a, **k: (_ for _ in ()).throw(ProviderError(429, RAW_429))
    svc = AnalysisService(repository, generator, SlidingWindowLimiter(100, 60))
    client = TestClient(create_app(svc, repository, Settings(session_secret="k" * 40),
                                   account_store_factory=lambda: store, search_fn=lambda *a, **k: []))
    response = client.post("/api/analyze", json=analyze_payload())
    assert response.status_code == 429
    assert response.json()["error"] == PROVIDER_RATE_LIMIT_MESSAGE
    assert "org_" not in response.text
