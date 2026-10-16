"""Backends de linguagem (Groq e Ollama) atras de uma interface unica.

`LLMRouter` escolhe o backend pelo nome do modelo; cada backend e uma classe com
inicializacao tardia, de modo que importar este modulo nao tem efeitos colaterais
alem de ler variaveis de ambiente.
"""

from __future__ import annotations

import os
from collections.abc import Generator, Sequence
from typing import Any, Optional, Protocol

from dotenv import load_dotenv

from domain import BackendUnavailableError

load_dotenv()

Message = dict[str, str]

GROQ_MODEL_MAP = {
    "GPT-OSS 120B (Groq)": "openai/gpt-oss-120b",
    "GPT-OSS 20B (Groq)": "openai/gpt-oss-20b",
    "Qwen 3.6 27B (Groq)": "qwen/qwen3.6-27b",
    "Qwen 3.8 27B (Groq)": "qwen/qwen3.8-27b",
}
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"

LOCAL_MODEL_MAP = {
    "Llama (local)": "llama3.2",
}

REQUEST_TIMEOUT_SECONDS = 120


class LLMBackend(Protocol):
    name: str

    def handles(self, model: str) -> bool: ...

    def is_available(self) -> bool: ...

    def generate(self, messages: Sequence[Message], model: str) -> str: ...

    def stream(self, messages: Sequence[Message], model: str) -> Generator[str, None, None]: ...


class GroqBackend:
    name = "groq"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client: Optional[object] = None

    def handles(self, model: str) -> bool:
        return model in GROQ_MODEL_MAP

    def is_available(self) -> bool:
        return bool(self._api_key)

    def _get_client(self) -> Any:
        if self._client is None:
            from groq import Groq

            self._client = Groq(api_key=self._api_key)
        return self._client

    @staticmethod
    def _model_id(model: str) -> str:
        return GROQ_MODEL_MAP.get(model, DEFAULT_GROQ_MODEL)

    def generate(self, messages: Sequence[Message], model: str) -> str:
        response = self._get_client().chat.completions.create(
            model=self._model_id(model),
            messages=list(messages),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        return response.choices[0].message.content or ""

    def stream(self, messages: Sequence[Message], model: str) -> Generator[str, None, None]:
        chunks = self._get_client().chat.completions.create(
            model=self._model_id(model),
            messages=list(messages),
            stream=True,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        accumulated = ""
        for chunk in chunks:
            accumulated += chunk.choices[0].delta.content or ""
            yield accumulated


class OllamaBackend:
    name = "ollama"

    def __init__(self) -> None:
        self._module: Optional[object] = None

    def handles(self, model: str) -> bool:
        return model in LOCAL_MODEL_MAP

    def is_available(self) -> bool:
        try:
            self._get_module()
        except RuntimeError:
            return False
        return True

    def _get_module(self) -> Any:
        if self._module is None:
            try:
                import ollama
            except ImportError as error:
                raise RuntimeError("O pacote 'ollama' nao esta instalado neste servidor.") from error
            self._module = ollama
        return self._module

    @staticmethod
    def _model_id(model: str) -> str:
        return LOCAL_MODEL_MAP.get(model, model)

    def generate(self, messages: Sequence[Message], model: str) -> str:
        client = self._get_module()
        model_id = self._model_id(model)
        client.pull(model_id)
        return client.chat(model=model_id, messages=list(messages))["message"]["content"]

    def stream(self, messages: Sequence[Message], model: str) -> Generator[str, None, None]:
        client = self._get_module()
        model_id = self._model_id(model)
        client.pull(model_id)
        accumulated = ""
        for chunk in client.chat(model=model_id, messages=list(messages), stream=True):
            accumulated += chunk["message"]["content"] or ""
            yield accumulated


class LLMRouter:
    """Despacha cada modelo para o backend que o atende."""

    def __init__(self, backends: Sequence[LLMBackend]) -> None:
        self._backends: list[LLMBackend] = list(backends)

    def _backend_for(self, model: str) -> LLMBackend:
        for backend in self._backends:
            if backend.handles(model):
                if not backend.is_available():
                    raise BackendUnavailableError(self._unavailable_message(backend, model))
                return backend
        raise BackendUnavailableError(f"Modelo desconhecido: '{model}'.")

    @staticmethod
    def _unavailable_message(backend: LLMBackend, model: str) -> str:
        if backend.name == "ollama":
            return (
                f"O modelo local '{model}' exige o Ollama instalado e em execucao nesta maquina, "
                "o que nao esta disponivel neste servidor. Selecione um dos modelos (Groq)."
            )
        return "Nenhum backend de LLM disponivel. Configure a variavel GROQ_API_KEY."

    def ensure_available(self, model: str) -> None:
        self._backend_for(model)

    def has_any_backend(self) -> bool:
        return any(backend.is_available() for backend in self._backends)

    def generate(self, messages: Sequence[Message], model: str) -> str:
        return self._backend_for(model).generate(messages, model)

    def stream(self, messages: Sequence[Message], model: str) -> Generator[str, None, None]:
        return self._backend_for(model).stream(messages, model)


GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
USE_GROQ = bool(GROQ_API_KEY)

_router = LLMRouter([GroqBackend(GROQ_API_KEY), OllamaBackend()])


def get_router() -> LLMRouter:
    return _router


def generate_response(messages: Sequence[Message], model: str) -> str:
    return _router.generate(messages, model)


def generate_response_stream(messages: Sequence[Message], model: str) -> Generator[str, None, None]:
    return _router.stream(messages, model)
