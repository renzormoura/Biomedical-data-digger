"""Fase 1: cache de resultados, deduplicacao concorrente e cotas no AnalysisService e na API."""

import threading
import time

import pytest
from fastapi.testclient import TestClient

import pages
from config import Settings
from domain import BackendUnavailableError, Completion, NexusError, RateLimitedError
from prompt_builders import build_message_pontos_chave, build_message_sumario
from quota import QuotaManager
from ratelimit import SlidingWindowLimiter
from test_web import FakeGenerator as WebFakeGenerator
from test_web import analyze_payload
from test_workflow import ABSTRACT, CountingResolver, FakeGenerator
from usage import UsageLog
from web import create_app
from workflow import AnalysisService, ArticleRepository, Filters


def make(gen=None, *, limit=100, quota=None, log=None, **kwargs):
    gen = gen or FakeGenerator(usage=(1000, 300))
    repository = ArticleRepository(CountingResolver())
    service = AnalysisService(repository, gen, SlidingWindowLimiter(limit, 60), usage_log=log, quota=quota, **kwargs)
    return service, gen, repository


def run(service, label="S", builder=build_message_sumario, **kwargs):
    kwargs.setdefault("client_id", "ip:1.1.1.1")
    return service.analyze("33984217", "m", builder, label, **kwargs)


# ------------------------------------------------------------------ cache
def test_identical_request_is_served_from_cache_without_calling_the_model():
    service, gen, _ = make()
    first = run(service)
    second = run(service)
    assert len(gen.calls) == 1
    assert first.cached is False and first.tokens == 1300
    assert second.cached is True and second.tokens == 0
    assert str(first) == str(second)


def test_cache_key_separates_filters_model_button_label_and_flags():
    service, gen, _ = make()
    run(service)
    run(service, filters=Filters(tom="Didático"))
    service.analyze("33984217", "outro-modelo", build_message_sumario, "S", client_id="x")
    run(service, builder=build_message_pontos_chave)
    run(service, label="Outro rotulo")
    run(service, clinical=True)
    run(service, check_numbers=False)
    assert len(gen.calls) == 7
    run(service)  # o primeiro continua em cache
    assert len(gen.calls) == 7


def test_equivalent_article_ids_share_one_cache_entry():
    service, gen, _ = make()
    service.analyze("33984217", "m", build_message_sumario, "S")
    service.analyze("https://pubmed.ncbi.nlm.nih.gov/33984217/", "m", build_message_sumario, "S")
    assert len(gen.calls) == 1


def test_failures_are_not_cached():
    class Flaky(FakeGenerator):
        def complete(self, messages, model, options=None):
            self.calls.append(1)
            if len(self.calls) == 1:
                raise RuntimeError("503")
            return Completion("ok", 10, 5)

    service, gen, _ = make(Flaky())
    with pytest.raises(NexusError):
        run(service)
    assert "ok" in run(service)
    assert len(gen.calls) == 2


def test_cache_hit_does_not_consume_the_rate_limit_and_works_without_backend():
    service, gen, _ = make(limit=1)
    run(service)
    assert run(service).cached  # limite 1 ja foi usado, mas o acerto e gratis
    gen.available = False
    assert run(service).cached  # backend fora do ar: o cache ainda responde
    with pytest.raises(BackendUnavailableError):
        run(service, label="nao-cacheado")


def test_cache_can_be_disabled_and_entries_expire():
    service, gen, _ = make(cache_results=False)
    run(service)
    run(service)
    assert len(gen.calls) == 2

    from cache import TTLCache

    class Clock:
        now = 0.0

        def __call__(self):
            return self.now

    clock = Clock()
    service2, gen2, _ = make(result_cache=TTLCache(10, ttl=60, clock=clock))
    run(service2)
    clock.now = 59
    run(service2)
    clock.now = 61
    run(service2)
    assert len(gen2.calls) == 2


def test_compare_is_cached_but_audit_is_not():
    service, gen, _ = make()
    service.compare("33984217", "33984218", "Eficácia", "m")
    again = service.compare("33984217", "33984218", "Eficácia", "m")
    assert again.cached and len(gen.calls) == 1
    service.audit("33984217", "m", "resposta")
    service.audit("33984217", "m", "resposta")
    assert len(gen.calls) == 3


def test_cache_hits_are_recorded_in_usage_log_with_zero_tokens():
    log = UsageLog()
    service, *_ = make(log=log)
    run(service, usage_key="geral/sumario")
    run(service, usage_key="geral/sumario")
    stats = log.snapshot()["by_key"]["geral/sumario"]
    assert stats["calls"] == 2 and stats["cache_hits"] == 1 and stats["prompt_tokens"] == 1000


# ------------------------------------------------------------------ deduplicacao concorrente
def test_simultaneous_identical_requests_call_the_model_once():
    started, release = threading.Event(), threading.Event()

    class Slow(FakeGenerator):
        def complete(self, messages, model, options=None):
            self.calls.append(1)
            started.set()
            release.wait(5)
            return Completion("resposta", 100, 50)

    service, gen, _ = make(Slow(), limit=2)
    replies = []
    threads = [threading.Thread(target=lambda: replies.append(run(service))) for _ in range(4)]
    threads[0].start()
    assert started.wait(5)
    for thread in threads[1:]:
        thread.start()
    time.sleep(0.2)
    release.set()
    for thread in threads:
        thread.join(5)
    assert len(gen.calls) == 1 and len(replies) == 4
    assert sorted(reply.cached for reply in replies) == [False, True, True, True]


# ------------------------------------------------------------------ cotas
def test_quota_blocks_after_budget_is_spent_and_never_calls_the_model():
    quota = QuotaManager(guest_budget=1500, user_budget=10_000)
    service, gen, _ = make(quota=quota)
    first = run(service, label="A")  # gasta 1.300
    assert first.quota_remaining == 200
    run(service, label="B")  # ultrapassa (cota so barra a chamada seguinte)
    with pytest.raises(RateLimitedError, match="Cota diária"):
        run(service, label="C")
    assert len(gen.calls) == 2


def test_quota_is_per_identity_and_users_get_the_larger_budget():
    quota = QuotaManager(guest_budget=100, user_budget=50_000)
    service, *_ = make(quota=quota)
    run(service, label="A", client_id="ip:1.1.1.1")
    with pytest.raises(RateLimitedError):
        run(service, label="B", client_id="ip:1.1.1.1")
    run(service, label="B", client_id="ip:2.2.2.2")
    run(service, label="B", client_id="u:ana@x.com")
    run(service, label="C", client_id="u:ana@x.com")


def test_cache_hits_do_not_charge_the_quota():
    quota = QuotaManager(guest_budget=2000, user_budget=2000)
    service, *_ = make(quota=quota)
    run(service)
    remaining = quota.remaining("ip:1.1.1.1")
    for _ in range(5):
        assert run(service).cached
    assert quota.remaining("ip:1.1.1.1") == remaining


def test_quota_charge_uses_estimate_when_provider_gives_no_usage():
    quota = QuotaManager(guest_budget=100_000, user_budget=100_000)
    service, *_ = make(FakeGenerator("texto de resposta"), quota=quota)
    reply = run(service)
    assert 100_000 - quota.remaining("ip:1.1.1.1") == reply.tokens and reply.tokens > 500


def test_quota_applies_to_audit_and_compare_too():
    quota = QuotaManager(guest_budget=100, user_budget=100)
    service, *_ = make(quota=quota)
    service.audit("33984217", "m", "resposta", client_id="ip:9.9.9.9")
    with pytest.raises(RateLimitedError):
        service.compare("33984217", "33984218", "Eficácia", "m", client_id="ip:9.9.9.9")


def test_reply_is_still_a_plain_string():
    service, *_ = make()
    reply = run(service)
    assert isinstance(reply, str) and reply.startswith("---") and "Sumário" not in reply.cached.__class__.__name__
    assert ABSTRACT[:5] not in str(reply)  # o abstract nao vaza na resposta


# ------------------------------------------------------------------ API
@pytest.fixture
def api(tmp_path, monkeypatch):
    from account_store import AccountStore

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "a.sqlite3"))
    store = AccountStore()
    store.initialize()
    repository = ArticleRepository(lambda raw: ("Titulo", ABSTRACT, "F"))

    def build(guest_budget=0, user_budget=0):
        generator = WebFakeGenerator()
        service = AnalysisService(
            repository, generator, SlidingWindowLimiter(100, 60),
            quota=QuotaManager(guest_budget, user_budget),
        )
        settings = Settings(session_secret="k" * 40, login_attempts_per_minute=50)
        app = create_app(service, repository, settings, account_store_factory=lambda: store,
                         search_fn=lambda *a, **k: [])
        return TestClient(app), generator

    return build


def test_api_reports_meta_and_marks_repeats_as_cached(api):
    client, generator = api()
    first = client.post("/api/analyze", json=analyze_payload()).json()["meta"]
    second = client.post("/api/analyze", json=analyze_payload()).json()["meta"]
    assert first == {"cached": False, "tokens": 200, "quota_remaining": None}
    assert second["cached"] is True and second["tokens"] == 0
    assert len(generator.calls) == 1


def test_api_returns_429_with_clear_message_when_daily_quota_is_exhausted(api):
    client, _ = api(guest_budget=150)
    ok = client.post("/api/analyze", json=analyze_payload(button="sumario"))
    assert ok.json()["meta"]["quota_remaining"] == 0
    blocked = client.post("/api/analyze", json=analyze_payload(button="resumo"))
    assert blocked.status_code == 429 and "Cota diária" in blocked.json()["error"]
    # repetir a analise ja feita continua funcionando (cache nao gasta cota)
    assert client.post("/api/analyze", json=analyze_payload(button="sumario")).status_code == 200


def test_api_logged_in_user_gets_the_user_budget(api):
    client, _ = api(guest_budget=100, user_budget=100_000)
    client.post("/api/auth/register", json={"email": "ana@exemplo.com", "password": "senha-forte-123"})
    for button in ("sumario", "resumo", "pontos-chave"):
        assert client.post("/api/analyze", json=analyze_payload(button=button)).status_code == 200
    guest = TestClient(client.app)
    # o cache e compartilhado: o que a conta ja gerou chega ao visitante sem custo
    assert guest.post("/api/analyze", json=analyze_payload(button="sumario")).json()["meta"]["cached"] is True
    # botoes ineditos gastam a cota do visitante (100 tokens): o primeiro passa, o segundo e barrado
    assert guest.post("/api/analyze", json=analyze_payload(button="resumo-introdutorio")).status_code == 200
    assert guest.post("/api/analyze", json=analyze_payload(button="resumo-academico")).status_code == 429


def test_settings_budgets_come_from_environment(monkeypatch):
    monkeypatch.setenv("DAILY_TOKEN_BUDGET_GUEST", "1234")
    monkeypatch.setenv("DAILY_TOKEN_BUDGET_USER", "0")
    settings = Settings.from_env()
    assert (settings.daily_token_budget_guest, settings.daily_token_budget_user) == (1234, 0)
    monkeypatch.setenv("DAILY_TOKEN_BUDGET_GUEST", "-1")
    with pytest.raises(ValueError):
        Settings.from_env()


def test_pages_still_expose_every_button_after_cache_changes():
    assert all(button.id for page in pages.ALL_PAGES for button in page.buttons())
