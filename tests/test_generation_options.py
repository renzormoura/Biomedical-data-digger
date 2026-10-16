"""Fase 2: opcoes de geracao, saida truncada e raciocinio reduzido so onde e seguro."""

import sys
import types
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import pages
import prompt_builders as pb
from config import Settings
from domain import Completion, DiggerError
from generation import DEFAULT_MAX_TOKENS, GenerationOptions, GenerationPolicy
from llm_service import GroqBackend, OllamaBackend
from prompt_builders import build_message_sumario
from ratelimit import SlidingWindowLimiter
from test_llm_backends import MSGS
from test_web import FakeGenerator as WebFakeGenerator
from test_web import analyze_payload
from test_workflow import CountingResolver, FakeGenerator
from web import create_app
from workflow import TRUNCATION_NOTICE, AnalysisService, ArticleRepository, Filters


# ------------------------------------------------------------------ politica
def test_policy_caps_depend_on_detail_and_fall_back_to_default():
    policy = GenerationPolicy()
    assert policy.for_detail("Resumido").max_output_tokens < policy.for_detail("Completo").max_output_tokens
    assert policy.for_detail("Completo").max_output_tokens < policy.for_detail("Ultra-detalhado").max_output_tokens
    assert policy.for_detail("").max_output_tokens == DEFAULT_MAX_TOKENS
    assert policy.for_detail("desconhecido").max_output_tokens == DEFAULT_MAX_TOKENS
    assert policy.for_detail().temperature == 0.2


def test_policy_reasoning_override_and_validation():
    policy = GenerationPolicy(reasoning_effort="medium")
    assert policy.for_detail("", "low").reasoning_effort == "low"
    assert policy.for_detail("").reasoning_effort == "medium"
    assert GenerationPolicy().for_detail("").reasoning_effort is None
    with pytest.raises(ValueError):
        policy.for_detail("", "extremo")
    with pytest.raises(ValueError):
        GenerationPolicy(reasoning_effort="x")
    with pytest.raises(ValueError):
        GenerationPolicy(temperature=3)
    with pytest.raises(ValueError):
        GenerationPolicy(default_max_tokens=10)


def test_temperature_setting_is_validated(monkeypatch):
    monkeypatch.setenv("LLM_TEMPERATURE", "0.5")
    assert Settings.from_env().llm_temperature == 0.5
    for bad in ("abc", "-1", "2.5"):
        monkeypatch.setenv("LLM_TEMPERATURE", bad)
        with pytest.raises(ValueError, match="LLM_TEMPERATURE"):
            Settings.from_env()
    monkeypatch.delenv("LLM_TEMPERATURE")
    assert Settings.from_env().llm_temperature == 0.2


# ------------------------------------------------------------------ backends
def _groq_with_capture(monkeypatch, finish_reason="stop", content="ok"):
    captured = {}
    client = MagicMock()

    def create(**kwargs):
        captured.update(kwargs)
        choice = types.SimpleNamespace(message=types.SimpleNamespace(content=content), finish_reason=finish_reason)
        return types.SimpleNamespace(choices=[choice], usage=types.SimpleNamespace(prompt_tokens=10, completion_tokens=5))

    client.chat.completions.create.side_effect = create
    module = types.ModuleType("groq")
    module.Groq = MagicMock(return_value=client)
    monkeypatch.setitem(sys.modules, "groq", module)
    return captured


def test_groq_receives_only_the_options_the_model_supports(monkeypatch):
    captured = _groq_with_capture(monkeypatch)
    options = GenerationOptions(temperature=0.2, max_output_tokens=1500, reasoning_effort="low")
    GroqBackend("k").complete(MSGS, "GPT-OSS 20B (Groq)", options)
    assert captured["temperature"] == 0.2 and captured["max_completion_tokens"] == 1500
    assert captured["reasoning_effort"] == "low"

    captured.clear()
    GroqBackend("k").complete(MSGS, "Qwen 3.6 27B (Groq)", options)  # nao e gpt-oss: sem reasoning_effort
    assert "reasoning_effort" not in captured and captured["temperature"] == 0.2

    captured.clear()
    GroqBackend("k").complete(MSGS, "GPT-OSS 20B (Groq)", None)
    assert not {"temperature", "max_completion_tokens", "reasoning_effort"} & set(captured)


def test_groq_flags_truncated_answers(monkeypatch):
    _groq_with_capture(monkeypatch, finish_reason="length")
    assert GroqBackend("k").complete(MSGS, "GPT-OSS 20B (Groq)").truncated is True
    _groq_with_capture(monkeypatch, finish_reason="stop")
    assert GroqBackend("k").complete(MSGS, "GPT-OSS 20B (Groq)").truncated is False


def test_ollama_maps_options_and_truncation(monkeypatch):
    fake = types.ModuleType("ollama")
    fake.pull = MagicMock()
    fake.chat = MagicMock(return_value={"message": {"content": "x"}, "done_reason": "length"})
    monkeypatch.setitem(sys.modules, "ollama", fake)
    result = OllamaBackend().complete(MSGS, "Llama (local)", GenerationOptions(temperature=0.1, max_output_tokens=300))
    assert fake.chat.call_args.kwargs["options"] == {"temperature": 0.1, "num_predict": 300}
    assert result.truncated is True
    OllamaBackend().complete(MSGS, "Llama (local)", None)
    assert "options" not in fake.chat.call_args.kwargs


# ------------------------------------------------------------------ servico
def make(gen=None, policy=GenerationPolicy(), **kwargs):
    gen = gen or FakeGenerator(usage=(1000, 300))
    service = AnalysisService(ArticleRepository(CountingResolver()), gen, SlidingWindowLimiter(100, 60),
                              policy=policy, **kwargs)
    return service, gen


def test_service_passes_policy_options_derived_from_detail_and_button():
    service, gen = make()
    service.analyze("33984217", "m", build_message_sumario, "S", Filters(detalhe="Resumido"), reasoning_effort="low")
    options = gen.options[-1]
    assert options.temperature == 0.2 and options.reasoning_effort == "low"
    assert options.max_output_tokens == GenerationPolicy().for_detail("Resumido").max_output_tokens


def test_service_without_policy_uses_provider_defaults():
    service, gen = make(policy=None)
    service.analyze("33984217", "m", build_message_sumario, "S", reasoning_effort="low")
    assert gen.options[-1] is None


def test_reasoning_effort_is_part_of_the_cache_key():
    service, gen = make()
    service.analyze("33984217", "m", build_message_sumario, "S")
    service.analyze("33984217", "m", build_message_sumario, "S", reasoning_effort="low")
    service.analyze("33984217", "m", build_message_sumario, "S", reasoning_effort="low")
    assert len(gen.calls) == 2


def test_audit_and_compare_use_default_options():
    service, gen = make()
    service.audit("33984217", "m", "resposta")
    service.compare("33984217", "33984218", "Eficácia", "m")
    assert all(o.reasoning_effort is None and o.temperature == 0.2 for o in gen.options)


class Truncating(FakeGenerator):
    def complete(self, messages, model, options=None):
        super().complete(messages, model, options)
        return Completion("resposta incompleta", 100, 50, truncated=True)


def test_truncated_answers_are_flagged_and_never_cached():
    service, gen = make(Truncating())
    first = service.analyze("33984217", "m", build_message_sumario, "S")
    assert TRUNCATION_NOTICE in first
    service.analyze("33984217", "m", build_message_sumario, "S")
    assert len(gen.calls) == 2  # nao veio do cache


def test_truncated_audit_and_compare_carry_the_notice():
    service, _ = make(Truncating())
    assert TRUNCATION_NOTICE in service.audit("33984217", "m", "resposta")
    assert TRUNCATION_NOTICE in service.compare("33984217", "33984218", "Eficácia", "m")


def test_empty_model_output_is_an_error_not_a_blank_result():
    class Empty(FakeGenerator):
        def complete(self, messages, model, options=None):
            return Completion("   ", 100, 900, truncated=True)

    service, _ = make(Empty())
    with pytest.raises(DiggerError, match="não devolveu texto.*limite de tamanho"):
        service.analyze("33984217", "m", build_message_sumario, "S")


# ------------------------------------------------------------------ paginas e API
def test_only_allowlisted_low_risk_buttons_reduce_reasoning():
    for page in pages.ALL_PAGES:
        for button in page.buttons():
            if button.reasoning_effort:
                assert button.builder in pages.LOW_REASONING, f"{page.key}/{button.id}"
                assert button.reasoning_effort == "low"


def test_high_risk_builders_never_reduce_reasoning():
    risky = [
        pb.build_message_critica_metodologica, pb.build_message_estatisticas, pb.build_message_confiabilidade,
        pb.build_message_medicamentos, pb.build_message_conduta_urgencia, pb.build_message_alertas,
        pb.build_message_checklist, pb.build_message_populacoes_especiais, pb.build_message_interacoes_medicamentosas,
        pb.build_message_reacoes_adversas, pb.build_message_resumo_clinico, pb.build_message_pico,
        pb.build_message_medidas_associacao, pb.build_message_vieses_confusao, pb.build_message_questoes_multipla_escolha,
        pb.build_message_disponibilidade_sus, pb.build_message_vigilancia_sanitaria, pb.build_message_aplicabilidade_br,
    ]
    assert not [b.__name__ for b in risky if b in pages.LOW_REASONING]


@pytest.fixture
def client_and_gen(tmp_path, monkeypatch):
    from account_store import AccountStore

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "a.sqlite3"))
    store = AccountStore()
    store.initialize()
    repository = ArticleRepository(lambda raw: ("Titulo", "Em 1200 pacientes a mortalidade caiu de 12,5% para 8,1%.", "F"))
    generator = WebFakeGenerator()
    service = AnalysisService(repository, generator, SlidingWindowLimiter(100, 60), policy=GenerationPolicy())
    app = create_app(service, repository, Settings(session_secret="k" * 40),
                     account_store_factory=lambda: store, search_fn=lambda *a, **k: [])
    return TestClient(app), generator


def test_api_reduces_reasoning_for_low_risk_buttons_on_general_pages(client_and_gen):
    client, generator = client_and_gen
    client.post("/api/analyze", json=analyze_payload(page="geral", button="sumario"))
    assert generator.options[-1].reasoning_effort == "low"
    client.post("/api/analyze", json=analyze_payload(page="geral", button="critica-metodologica"))
    assert generator.options[-1].reasoning_effort is None


def test_api_never_reduces_reasoning_on_clinical_pages_even_for_the_same_button(client_and_gen):
    client, generator = client_and_gen
    for page in ("saude_publica", "medicina"):
        client.post("/api/analyze", json=analyze_payload(page=page, button="sumario" if page == "saude_publica" else "resumo-clinico"))
        assert generator.options[-1].reasoning_effort is None, page
    assert generator.options[-1].temperature == 0.2
