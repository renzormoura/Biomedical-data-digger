"""Modelo de dominio: tipos que circulam entre resolucao, cache, LLM e UI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class InputType(str, Enum):
    PMID = "pmid"
    PMCID = "pmcid"
    DOI = "doi"
    ARXIV = "arxiv"
    OPENALEX = "openalex"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    GOOGLE_SCHOLAR = "google_scholar"
    GENERIC_URL = "generic_url"
    UNKNOWN = "unknown"


# Prefixos que os resolvedores legados usam para sinalizar falha no campo "titulo".
# Centralizados aqui para que nenhum chamador dependa de strings espalhadas.
_FAILURE_TITLE_PREFIXES = (
    "Erro ao buscar",
    "Artigo nao encontrado",
    "Nenhum resultado encontrado",
    "Nao foi possivel ler a pagina",
    "No XML found",
    "No Title Found",
    "Titulo nao encontrado",
)


def is_failure_title(title: str) -> bool:
    """True quando `title` e uma mensagem de falha e nao o titulo de um artigo."""
    return any(title.startswith(prefix) for prefix in _FAILURE_TITLE_PREFIXES)


@dataclass(frozen=True)
class Completion:
    """Resposta de um LLM com o consumo de tokens quando o provedor o informa."""

    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    truncated: bool = False  # o provedor cortou a resposta por atingir o teto de saida

    @property
    def total_tokens(self) -> int | None:
        if self.prompt_tokens is None and self.completion_tokens is None:
            return None
        return (self.prompt_tokens or 0) + (self.completion_tokens or 0)


class DiggerError(Exception):
    """Erro esperado com mensagem segura para exibir ao usuario."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


class RateLimitedError(DiggerError):
    """O cliente excedeu o limite de uso (HTTP 429)."""


class SourceUnavailableError(DiggerError):
    """Uma fonte de artigos (Europe PMC, OpenAlex...) esta indisponivel (HTTP 503)."""


class BackendUnavailableError(DiggerError):
    """Nenhum backend de LLM apto a atender o modelo pedido."""


class NotFoundError(DiggerError):
    """O recurso pedido nao existe (HTTP 404)."""


class LimitReachedError(DiggerError):
    """Um limite de uso (itens, listas...) foi atingido (HTTP 409)."""


class ArticleNotFoundError(NotFoundError):
    """Nenhum abstract utilizavel foi encontrado para a entrada."""


@dataclass(frozen=True)
class Article:
    """Artigo resolvido. `abstract` nunca e vazio em instancias validas."""

    identifier: str
    title: str
    abstract: str
    source: str = ""
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.abstract.strip():
            raise ValueError("Article exige abstract nao vazio.")
