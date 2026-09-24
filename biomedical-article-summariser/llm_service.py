"""Adaptador para os backends de linguagem usados pela aplicacao."""

import os
from typing import Dict, Generator, List

import gradio as gr

from dotenv import load_dotenv

load_dotenv()

Message = Dict[str, str]
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
USE_GROQ = bool(GROQ_API_KEY)

GROQ_MODEL_MAP = {
    "GPT-OSS 120B (Groq)": "openai/gpt-oss-120b",
    "GPT-OSS 20B (Groq)": "openai/gpt-oss-20b",
    "Qwen 3.6 27B (Groq)": "qwen/qwen3.6-27b",
    "Qwen 3.8 27B (Groq)": "qwen/qwen3.8-27b",
}

LOCAL_MODEL_MAP = {
    "Llama (local)": "llama3.2",
}

ollama = None


if USE_GROQ:
    from groq import Groq

    groq_client = Groq(api_key=GROQ_API_KEY)
else:
    groq_client = None


def _is_local_model(model: str) -> bool:
    return model in LOCAL_MODEL_MAP or (not USE_GROQ and model not in GROQ_MODEL_MAP)


def _resolve_ollama_model(model: str) -> str:
    return LOCAL_MODEL_MAP.get(model, model)


def _get_ollama():
    global ollama
    if ollama is None:
        try:
            import ollama as ollama_client
        except ImportError as error:
            raise RuntimeError(
                "O pacote 'ollama' não está instalado neste servidor. "
                "Escolha um dos modelos (Groq) ou rode o app localmente com o Ollama instalado."
            ) from error
        ollama = ollama_client
    return ollama


def _no_backend_error(model: str) -> gr.Error:
    if _is_local_model(model):
        return gr.Error(
            f"O modelo local '{model}' exige o Ollama instalado e em execução na máquina "
            "(http://localhost:11434), o que não está disponível neste servidor. "
            "Selecione um dos modelos (Groq) na lista."
        )
    return gr.Error(
        "Nenhum backend de LLM disponível. Configure a variável GROQ_API_KEY "
        "para usar os modelos (Groq) ou rode o app localmente com o Ollama instalado."
    )


def generate_response_stream(messages: List[Message], model: str) -> Generator[str, None, None]:
    if _is_local_model(model):
        client = _get_ollama()
        ollama_model = _resolve_ollama_model(model)
        client.pull(ollama_model)
        accumulated = ""
        for chunk in client.chat(model=ollama_model, messages=messages, stream=True):
            accumulated += chunk["message"]["content"] or ""
            yield accumulated
        return
    if groq_client is None:
        raise _no_backend_error(model)
    stream = groq_client.chat.completions.create(
        model=GROQ_MODEL_MAP.get(model, "openai/gpt-oss-120b"),
        messages=messages,
        stream=True,
        timeout=120,
    )
    accumulated = ""
    for chunk in stream:
        accumulated += chunk.choices[0].delta.content or ""
        yield accumulated


def generate_response(messages: List[Message], model: str) -> str:
    if _is_local_model(model):
        client = _get_ollama()
        ollama_model = _resolve_ollama_model(model)
        client.pull(ollama_model)
        response = client.chat(model=ollama_model, messages=messages)
        return response["message"]["content"]
    if groq_client is None:
        raise _no_backend_error(model)
    response = groq_client.chat.completions.create(
        model=GROQ_MODEL_MAP.get(model, "openai/gpt-oss-120b"),
        messages=messages,
        timeout=120,
    )
    return response.choices[0].message.content
