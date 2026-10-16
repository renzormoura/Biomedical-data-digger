import pytest

from domain import BackendUnavailableError, Completion
from llm_service import GroqBackend, LLMRouter, OllamaBackend


class FakeBackend:
    def __init__(self, name, models, available=True):
        self.name = name
        self._models = set(models)
        self._available = available
        self.calls = []

    def handles(self, model):
        return model in self._models

    def is_available(self):
        return self._available

    def complete(self, messages, model):
        self.calls.append((list(messages), model))
        return Completion(f"{self.name}:{model}", 7, 3)

    def generate(self, messages, model):
        return self.complete(messages, model).text

    def stream(self, messages, model):
        yield self.generate(messages, model)


MSGS = [{"role": "user", "content": "oi"}]


def test_routes_by_model_name():
    groq, local = FakeBackend("groq", {"G"}), FakeBackend("ollama", {"L"})
    router = LLMRouter([groq, local])
    assert router.generate(MSGS, "G") == "groq:G"
    assert router.generate(MSGS, "L") == "ollama:L"
    assert len(groq.calls) == 1 and len(local.calls) == 1


def test_unknown_model_is_a_domain_error():
    with pytest.raises(BackendUnavailableError):
        LLMRouter([FakeBackend("groq", {"G"})]).generate(MSGS, "???")


def test_unavailable_backend_gives_actionable_message():
    router = LLMRouter([FakeBackend("groq", {"G"}, available=False)])
    with pytest.raises(BackendUnavailableError, match="GROQ_API_KEY"):
        router.ensure_available("G")


def test_unavailable_local_backend_message_mentions_ollama():
    router = LLMRouter([FakeBackend("ollama", {"L"}, available=False)])
    with pytest.raises(BackendUnavailableError, match="Ollama"):
        router.ensure_available("L")


def test_has_any_backend():
    assert not LLMRouter([FakeBackend("g", {"G"}, available=False)]).has_any_backend()
    assert LLMRouter([FakeBackend("g", {"G"}, available=False), FakeBackend("o", {"L"})]).has_any_backend()


def test_groq_backend_without_key_is_unavailable_and_never_builds_client():
    backend = GroqBackend("")
    assert not backend.is_available()
    assert backend._client is None


def test_groq_backend_handles_only_known_models():
    backend = GroqBackend("k")
    assert backend.handles("GPT-OSS 20B (Groq)")
    assert not backend.handles("Llama (local)")


def test_ollama_backend_handles_local_only():
    backend = OllamaBackend()
    assert backend.handles("Llama (local)")
    assert not backend.handles("GPT-OSS 20B (Groq)")
