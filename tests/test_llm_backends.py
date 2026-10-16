"""Backends reais com SDKs substituidos por dublês (sem rede)."""

import sys
import types
from unittest.mock import MagicMock

from llm_service import GroqBackend, LLMRouter, OllamaBackend

MSGS = [{"role": "user", "content": "oi"}]


def fake_groq_module(reply="resposta", chunks=("a", "b", None)):
    client = MagicMock()
    client.chat.completions.create.side_effect = lambda **kw: (
        iter(
            [types.SimpleNamespace(choices=[types.SimpleNamespace(delta=types.SimpleNamespace(content=c))]) for c in chunks]
        )
        if kw.get("stream")
        else types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=reply))])
    )
    module = types.ModuleType("groq")
    module.Groq = MagicMock(return_value=client)
    return module, client


def test_groq_generate_maps_model_and_timeout(monkeypatch):
    module, client = fake_groq_module()
    monkeypatch.setitem(sys.modules, "groq", module)
    backend = GroqBackend("key")
    assert backend.generate(MSGS, "GPT-OSS 20B (Groq)") == "resposta"
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "openai/gpt-oss-20b" and kwargs["timeout"] == 120
    backend.generate(MSGS, "GPT-OSS 20B (Groq)")
    module.Groq.assert_called_once_with(api_key="key")  # cliente criado uma unica vez


def test_groq_none_content_becomes_empty_string(monkeypatch):
    module, _ = fake_groq_module(reply=None)
    monkeypatch.setitem(sys.modules, "groq", module)
    assert GroqBackend("key").generate(MSGS, "GPT-OSS 20B (Groq)") == ""


def test_groq_stream_accumulates(monkeypatch):
    module, _ = fake_groq_module()
    monkeypatch.setitem(sys.modules, "groq", module)
    assert list(GroqBackend("key").stream(MSGS, "GPT-OSS 20B (Groq)")) == ["a", "ab", "ab"]


def test_ollama_generate_and_stream(monkeypatch):
    fake = types.ModuleType("ollama")
    fake.pull = MagicMock()
    fake.chat = MagicMock(
        side_effect=lambda **kw: iter([{"message": {"content": "x"}}, {"message": {"content": "y"}}])
        if kw.get("stream")
        else {"message": {"content": "local"}}
    )
    monkeypatch.setitem(sys.modules, "ollama", fake)
    backend = OllamaBackend()
    assert backend.is_available()
    assert backend.generate(MSGS, "Llama (local)") == "local"
    fake.pull.assert_called_with("llama3.2")
    assert list(backend.stream(MSGS, "Llama (local)")) == ["x", "xy"]


def test_ollama_unavailable_when_package_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "ollama", None)  # forca ImportError
    assert not OllamaBackend().is_available()


def test_router_stream_delegates(monkeypatch):
    module, _ = fake_groq_module()
    monkeypatch.setitem(sys.modules, "groq", module)
    router = LLMRouter([GroqBackend("k"), OllamaBackend()])
    assert list(router.stream(MSGS, "GPT-OSS 20B (Groq)"))[-1] == "ab"
