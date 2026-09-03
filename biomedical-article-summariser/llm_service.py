"""Adaptador para os backends de linguagem usados pela aplicacao."""

import os
from typing import Dict, Generator, List

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
    "Llama (local)": "llama3.2",
}

if USE_GROQ:
    from groq import Groq

    groq_client = Groq(api_key=GROQ_API_KEY)
else:
    ollama = None


def generate_response_stream(messages: List[Message], model: str) -> Generator[str, None, None]:
    global ollama
    if ollama is None:
        import ollama as ollama_client
        ollama = ollama_client
    if USE_GROQ:
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
    else:
        ollama.pull(model)
        accumulated = ""
        for chunk in ollama.chat(model=model, messages=messages, stream=True):
            accumulated += chunk["message"]["content"] or ""
            yield accumulated


def generate_response(messages: List[Message], model: str) -> str:
    global ollama
    if ollama is None:
        import ollama as ollama_client
        ollama = ollama_client
    if USE_GROQ:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL_MAP.get(model, "openai/gpt-oss-120b"),
            messages=messages,
            timeout=120,
        )
        return response.choices[0].message.content
    ollama.pull(model)
    response = ollama.chat(model=model, messages=messages)
    return response["message"]["content"]
