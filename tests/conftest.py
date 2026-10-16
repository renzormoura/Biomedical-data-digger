"""Configuracao compartilhada: coloca o codigo-fonte no path e isola a rede."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "biomedical-article-summariser"))


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch):
    """Testes nunca fazem DNS real: todo host resolve para um IP publico fixo."""
    import security

    monkeypatch.setattr(security, "_resolve_host", lambda host: ["93.184.216.34"])


def make_response(content: bytes = b"", status: int = 200, headers: dict | None = None):
    """Response real do `requests`, com corpo em memoria (compativel com safe_get)."""
    import requests

    response = requests.Response()
    response.status_code = status
    response._content = content
    response._content_consumed = True
    response.headers.update(headers or {})
    return response
