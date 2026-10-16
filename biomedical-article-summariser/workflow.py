"""Casos de uso da aplicacao, independentes de Gradio.

A UI so traduz entradas/saidas; toda a orquestracao (resolver artigo, cache,
rate limit, prompt, LLM, verificacao de grounding) vive aqui e e testavel com
dependencias injetadas.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Optional, Protocol

import article_services
import citations
from cache import TTLCache
from domain import Article, ArticleNotFoundError, DiggerError, is_failure_title
from grounding import check_numeric_grounding
from prompt_builders import (
    build_dynamic_sys_prompt,
    build_message_auditoria_resposta,
    build_message_comparacao_artigos,
)
from ratelimit import RateLimitExceeded, SlidingWindowLimiter

Message = dict[str, str]
BuildFn = Callable[..., list[Message]]

MAX_SOURCE_CHARS = 12_000

CLINICAL_DISCLAIMER = (
    "\n\n---\n> ⚕️ **Apoio à leitura, não à decisão.** Conteúdo gerado por IA a partir apenas do "
    "título e do resumo do artigo. Não substitui bula, diretriz institucional, o texto completo "
    "nem o julgamento clínico. Confirme doses e condutas na fonte primária."
)


class Resolver(Protocol):
    def __call__(self, raw_input: str) -> tuple[str, str, str]: ...


class TextGenerator(Protocol):
    def ensure_available(self, model: str) -> None: ...

    def generate(self, messages: Sequence[Message], model: str) -> str: ...


def canonical_key(raw: str) -> str:
    """Chave de cache estavel: PMID, DOI ou URL do mesmo artigo colapsam em uma entrada."""
    input_type, value = article_services.detect_input_type(raw.strip())
    if input_type in ("doi", "arxiv", "openalex", "semantic_scholar"):
        value = value.lower()
    return f"{input_type}:{value}"


def wrap_source(tag: str, text: str) -> str:
    """Delimita texto nao confiavel; remove marcadores que permitiriam escapar do bloco."""
    cleaned = re.sub(r"<{3,}|>{3,}", " ", text)[:MAX_SOURCE_CHARS]
    return f"<<<{tag}_START>>>\n{cleaned}\n<<<{tag}_END>>>"


class ArticleRepository:
    """Resolve identificadores em `Article`, com cache LRU/TTL e erros tipados."""

    def __init__(self, resolver: Resolver = article_services.resolve_article, cache: Optional[TTLCache[Article]] = None) -> None:
        self._resolver = resolver
        self._cache: TTLCache[Article] = cache if cache is not None else TTLCache(max_size=128, ttl=3600)

    def peek(self, raw: str) -> Optional[Article]:
        if not raw or not raw.strip():
            return None
        return self._cache.get(canonical_key(raw))

    def get(self, raw: str) -> Article:
        if not raw or not raw.strip():
            raise DiggerError("Por favor, cole um ID ou URL de artigo antes de gerar a análise.")
        key = canonical_key(raw)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        try:
            title, abstract, source = self._resolver(raw.strip())
        except DiggerError:
            raise
        except Exception as error:
            raise DiggerError(f"Erro ao buscar artigo: {error}") from error
        if not abstract or not abstract.strip():
            raise ArticleNotFoundError(_not_found_message(title))
        article = Article(identifier=raw.strip(), title=title, abstract=abstract, source=source)
        self._cache.set(key, article)
        return article


def _not_found_message(title: str) -> str:
    if is_failure_title(title):
        return f"Não foi possível obter o artigo: {title}"
    return (
        f"Nenhum abstract encontrado para: {title}\n\n"
        "O artigo pode ser de acesso restrito (paywall). "
        "Tente buscar pelo DOI em outra fonte ou use um PMCID de artigo Open Access."
    )


@dataclass(frozen=True)
class Filters:
    publico: str = ""
    tom: str = ""
    idioma: str = ""
    detalhe: str = ""
    foco: str = ""

    def active(self) -> list[str]:
        return [value for value in (self.publico, self.tom, self.idioma, self.detalhe, self.foco) if value]

    def describe(self) -> str:
        return "  |  ".join(self.active()) or "Padrão"


class AnalysisService:
    def __init__(
        self,
        repository: ArticleRepository,
        generator: TextGenerator,
        limiter: SlidingWindowLimiter,
        citation_fetcher: Callable[[str], citations.CitationMetadata] = citations.fetch_citation_metadata,
    ) -> None:
        self._repository = repository
        self._generator = generator
        self._limiter = limiter
        self._citation_fetcher = citation_fetcher

    def _generate(self, messages: Sequence[Message], model: str, client_id: str, error_prefix: str) -> str:
        self._generator.ensure_available(model)
        try:
            self._limiter.check(client_id)
        except RateLimitExceeded as error:
            raise DiggerError(str(error)) from error
        try:
            return self._generator.generate(messages, model)
        except DiggerError:
            raise
        except Exception as error:
            raise DiggerError(f"{error_prefix}: {error}") from error

    def analyze(
        self,
        article_id: str,
        model: str,
        build_fn: BuildFn,
        label: str,
        filters: Filters | None = None,
        *,
        client_id: str = "local",
        clinical: bool = False,
        check_numbers: bool = True,
        footer: str = "",
    ) -> str:
        filters = filters or Filters()
        self._generator.ensure_available(model)
        article = self._repository.get(article_id)
        messages = build_fn(
            wrap_source("SOURCE_TITLE", article.title),
            wrap_source("SOURCE_ABSTRACT", article.abstract),
            sys_prompt=build_dynamic_sys_prompt(
                filters.publico, filters.tom, filters.idioma, filters.detalhe, filters.foco
            ),
        )
        summary = self._generate(messages, model, client_id, "Erro ao gerar resumo com a LLM")
        body = f"## Título do Artigo: {article.title}\n\n### Resumo:\n{summary}"
        if check_numbers:
            body += check_numeric_grounding(summary, f"{article.title}\n{article.abstract}").to_markdown()
        if clinical:
            body += CLINICAL_DISCLAIMER
        return f"---\n> **{label}**  ·  Filtros: *{filters.describe()}*\n\n---\n{body}{footer}"

    def audit(self, article_id: str, model: str, response_text: str, *, client_id: str = "local") -> str:
        if not response_text:
            raise DiggerError("Gere uma análise antes de executar a auditoria.")
        article = self._repository.get(article_id)
        messages = build_message_auditoria_resposta(
            wrap_source("SOURCE_TITLE", article.title),
            wrap_source("SOURCE_ABSTRACT", article.abstract),
            response_text,
        )
        audit = self._generate(messages, model, client_id, "Erro ao auditar a resposta")
        return f"---\n> **Auditoria da Resposta**\n\n---\n{audit}"

    def compare(
        self,
        article_id_a: str,
        article_id_b: str,
        analysis_type: str,
        model: str,
        *,
        medical_context: bool = False,
        client_id: str = "local",
    ) -> str:
        if not (article_id_a or "").strip() or not (article_id_b or "").strip():
            raise DiggerError("Informe os dois IDs ou URLs para comparar os artigos.")
        a = self._repository.get(article_id_a)
        b = self._repository.get(article_id_b)
        messages = build_message_comparacao_artigos(
            wrap_source("SOURCE_A_TITLE", a.title),
            wrap_source("SOURCE_A_ABSTRACT", a.abstract),
            wrap_source("SOURCE_B_TITLE", b.title),
            wrap_source("SOURCE_B_ABSTRACT", b.abstract),
            analysis_type=analysis_type,
            medical_context=medical_context,
        )
        comparison = self._generate(messages, model, client_id, "Erro ao comparar os artigos")
        suffix = CLINICAL_DISCLAIMER if medical_context else ""
        return f"---\n> **Comparação entre Artigos**\n\n---\n{comparison}{suffix}"

    def cite(self, article_id: str, style: str, *, client_id: str = "local") -> str:
        """Referencia formatada (ABNT/APA/Vancouver) a partir de registros oficiais, sem LLM."""
        if not (article_id or "").strip():
            raise DiggerError("Cole um DOI, PMID ou PMCID para gerar a referência.")
        try:
            self._limiter.check(client_id)
        except RateLimitExceeded as error:
            raise DiggerError(str(error)) from error
        meta = self._citation_fetcher(article_id)
        reference = citations.format_citation(meta, style)
        return (
            f"---\n> **Referência · {style}**\n\n---\n{reference}\n\n"
            "> Gerada automaticamente a partir do registro oficial (Crossref ou Europe PMC), "
            "sem uso de IA. Confira com as normas do seu curso antes de entregar."
        )
