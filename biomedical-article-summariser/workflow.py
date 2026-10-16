"""Casos de uso da aplicacao, independentes de framework web.

A UI so traduz entradas/saidas; toda a orquestracao (resolver artigo, cache,
rate limit, prompt, LLM, verificacao de grounding) vive aqui e e testavel com
dependencias injetadas.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Optional, Protocol

from loguru import logger

import article_services
import citations
import europepmc
from cache import SingleFlight, TTLCache
from domain import Article, ArticleNotFoundError, Completion, DiggerError, RateLimitedError, is_failure_title
from europepmc import EuropePmcRecord
from extraction import has_cues
from extraction_view import (
    PASSAGE_KINDS,
    blocked_markdown,
    overview_markdown,
    passages_markdown,
)
from generation import GenerationOptions, GenerationPolicy
from grounding import check_numeric_grounding
from injection import neutralize
from prompt_builders import (
    build_dynamic_sys_prompt,
    build_message_auditoria_resposta,
    build_message_comparacao_artigos,
)
from quota import QuotaExceeded, QuotaManager
from ratelimit import RateLimitExceeded, SlidingWindowLimiter
from usage import UsageLog, UsageRecord, client_kind, estimate_messages_tokens, estimate_tokens

Message = dict[str, str]
BuildFn = Callable[..., list[Message]]

MAX_SOURCE_CHARS = 12_000

CLINICAL_DISCLAIMER = (
    "\n\n---\n> ⚕️ **Apoio à leitura, não à decisão.** Conteúdo gerado por IA a partir apenas do "
    "título e do resumo do artigo. Não substitui bula, diretriz institucional, o texto completo "
    "nem o julgamento clínico. Confirme doses e condutas na fonte primária."
)


CLINICAL_EXTRACT_DISCLAIMER = (
    "\n\n---\n> ⚕️ **Apoio à leitura, não à decisão.** Trechos copiados apenas do título e do resumo do "
    "artigo, sem interpretação. Não substituem bula, diretriz institucional, o texto completo nem o "
    "julgamento clínico. Confirme doses e condutas na fonte primária."
)


class Resolver(Protocol):
    def __call__(self, raw_input: str) -> tuple[str, str, str]: ...


class TextGenerator(Protocol):
    def ensure_available(self, model: str) -> None: ...

    def complete(
        self, messages: Sequence[Message], model: str, options: GenerationOptions | None = None
    ) -> Completion: ...


def canonical_key(raw: str) -> str:
    """Chave de cache estavel: PMID, DOI ou URL do mesmo artigo colapsam em uma entrada."""
    input_type, value = article_services.detect_input_type(raw.strip())
    if input_type in ("doi", "arxiv", "openalex", "semantic_scholar"):
        value = value.lower()
    return f"{input_type}:{value}"


_BOILERPLATE = re.compile(
    r"(?:©|\(c\)\s*\d{4}|copyright\s*(?:©|\(c\))?\s*\d{4}|all rights reserved|"
    r"published by elsevier|this is an open access article|licensee|crown copyright)",
    re.IGNORECASE,
)


def strip_boilerplate(abstract: str) -> str:
    """Remove avisos de copyright/licenca no FIM do abstract (ruido que gasta token).

    So corta quando o aviso aparece depois de 60% do texto, para nunca apagar conteudo.
    """
    text = re.sub(r"^\s*abstract\s*[:.\-]?\s*", "", abstract, flags=re.IGNORECASE).strip()
    matches = [m.start() for m in _BOILERPLATE.finditer(text)]
    if matches and matches[0] == 0 and len(text) < 120:
        return ""  # o "abstract" e apenas um aviso de copyright
    if matches and matches[0] >= 0.6 * len(text):
        cut = text[: matches[0]].rstrip().rstrip(".;:-—· ")
        return cut + "." if cut else cut
    return text


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
        cleaned, removed = neutralize(strip_boilerplate(abstract))
        if not cleaned:
            raise ArticleNotFoundError(_not_found_message(title))
        warnings = (
            (
                f"o texto-fonte continha {removed} trecho(s) que pareciam instruções ao modelo; "
                "eles foram removidos antes da análise.",
            )
            if removed
            else ()
        )
        article = Article(identifier=raw.strip(), title=title, abstract=cleaned, source=source, warnings=warnings)
        self._cache.set(key, article)
        return article


PROVIDER_RATE_LIMIT_MESSAGE = (
    "O provedor de IA atingiu o limite de uso agora. Tente novamente em alguns minutos "
    "ou escolha outro modelo de linguagem."
)


def _provider_error(prefix: str, error: Exception) -> DiggerError:
    """Converte falhas do provedor em erro seguro: o texto cru pode trazer IDs internos.

    429 vira `RateLimitedError` com mensagem amigavel; erros HTTP exibem so o codigo; os
    detalhes completos vao para o log do servidor.
    """
    status = getattr(error, "status_code", None)
    logger.warning("Falha do provedor de LLM (status={}): {}", status, error)
    if status == 429:
        return RateLimitedError(PROVIDER_RATE_LIMIT_MESSAGE)
    if isinstance(status, int):
        return DiggerError(f"{prefix} (provedor respondeu HTTP {status}). Tente novamente em instantes.")
    return DiggerError(f"{prefix}: {error}")


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


class Reply(str):
    """Texto de resposta (str) com metadados da chamada.

    Continua sendo uma `str` para todos os usos existentes; `cached`, `tokens` e
    `quota_remaining` viajam junto do valor, sem estado compartilhado entre threads.
    """

    cached: bool
    tokens: int | None
    quota_remaining: int | None

    def __new__(
        cls, text: str, *, cached: bool = False, tokens: int | None = None, quota_remaining: int | None = None
    ) -> Reply:
        obj = super().__new__(cls, text)
        obj.cached = cached
        obj.tokens = tokens
        obj.quota_remaining = quota_remaining
        return obj


TRUNCATION_NOTICE = (
    "\n\n---\n> ✂️ **Resposta cortada:** o modelo atingiu o limite de tamanho antes de terminar. "
    "Tente o detalhe \"Resumido\" ou repita a análise."
)


@dataclass(frozen=True)
class _Outcome:
    text: str
    tokens: int | None
    cacheable: bool = True  # respostas cortadas nao entram no cache


RESULT_CACHE_SIZE = 512
RESULT_CACHE_TTL = 6 * 3600


def _digest(*parts: object) -> str:
    return hashlib.sha256("\x1f".join(str(part) for part in parts).encode("utf-8")).hexdigest()


class AnalysisService:
    def __init__(
        self,
        repository: ArticleRepository,
        generator: TextGenerator,
        limiter: SlidingWindowLimiter,
        citation_fetcher: Callable[[str], citations.CitationMetadata] = citations.fetch_citation_metadata,
        usage_log: UsageLog | None = None,
        quota: QuotaManager | None = None,
        result_cache: TTLCache[str] | None = None,
        cache_results: bool = True,
        policy: GenerationPolicy | None = None,
        metadata_fetcher: Callable[[str], EuropePmcRecord | None] = europepmc.fetch_record,
    ) -> None:
        self._repository = repository
        self._generator = generator
        self._limiter = limiter
        self._citation_fetcher = citation_fetcher
        self._usage_log = usage_log
        self._quota = quota
        self._policy = policy
        self._metadata_fetcher = metadata_fetcher
        self._records: TTLCache[tuple[EuropePmcRecord | None]] = TTLCache(RESULT_CACHE_SIZE, RESULT_CACHE_TTL)
        self._cache_results = cache_results
        self._results: TTLCache[str] = (
            result_cache if result_cache is not None else TTLCache(RESULT_CACHE_SIZE, RESULT_CACHE_TTL)
        )
        self._flight: SingleFlight[_Outcome] = SingleFlight()

    # -- geracao ----------------------------------------------------------
    def _options(self, detail: str = "", reasoning_effort: str | None = None) -> GenerationOptions | None:
        return self._policy.for_detail(detail, reasoning_effort) if self._policy is not None else None

    def _run(
        self,
        messages: Sequence[Message],
        model: str,
        client_id: str,
        error_prefix: str,
        usage_key: str,
        options: GenerationOptions | None = None,
    ) -> tuple[Completion, int]:
        """Chama o modelo respeitando limite por minuto e cota diaria; devolve (resposta, tokens)."""
        self._generator.ensure_available(model)
        if self._quota is not None:
            try:
                self._quota.check(client_id)
            except QuotaExceeded as error:
                raise RateLimitedError(str(error)) from error
        try:
            self._limiter.check(client_id)
        except RateLimitExceeded as error:
            raise RateLimitedError(str(error)) from error
        started = time.monotonic()
        try:
            completion = self._generator.complete(messages, model, options)
        except DiggerError:
            raise
        except Exception as error:
            raise _provider_error(error_prefix, error) from error
        tokens = self._record_usage(usage_key, model, client_id, messages, completion, started)
        if self._quota is not None:
            self._quota.charge(client_id, tokens)
        if not completion.text.strip():
            raise DiggerError(
                "O modelo não devolveu texto"
                + (" (atingiu o limite de tamanho)" if completion.truncated else "")
                + ". Tente novamente."
            )
        if self._policy is not None and len(completion.text.strip()) < self._policy.min_answer_chars:
            raise DiggerError(
                "A resposta do modelo veio curta demais para ser uma análise válida e foi descartada. "
                "Tente novamente."
            )
        return completion, tokens

    def _record_usage(
        self, usage_key: str, model: str, client_id: str, messages: Sequence[Message],
        completion: Completion, started: float,
    ) -> int:
        estimated = completion.prompt_tokens is None or completion.completion_tokens is None
        prompt = (
            completion.prompt_tokens if completion.prompt_tokens is not None else estimate_messages_tokens(messages)
        )
        generated = (
            completion.completion_tokens if completion.completion_tokens is not None
            else estimate_tokens(completion.text)
        )
        if self._usage_log is not None:
            self._usage_log.record(
                UsageRecord(
                    key=usage_key, model=model, prompt_tokens=prompt, completion_tokens=generated,
                    cached=False, estimated=estimated, latency_ms=round((time.monotonic() - started) * 1000),
                    client_kind=client_kind(client_id),
                )
            )
        return prompt + generated

    def _record_hit(self, usage_key: str, model: str, client_id: str) -> None:
        if self._usage_log is not None:
            self._usage_log.record(
                UsageRecord(
                    key=usage_key, model=model, prompt_tokens=0, completion_tokens=0, cached=True,
                    estimated=False, latency_ms=0, client_kind=client_kind(client_id),
                )
            )

    def _remaining(self, client_id: str) -> int | None:
        return self._quota.remaining(client_id) if self._quota is not None else None

    # -- cache e deduplicacao -----------------------------------------------
    def _serve(
        self,
        key: str,
        *,
        client_id: str,
        model: str,
        usage_key: str,
        compute: Callable[[], _Outcome],
    ) -> Reply:
        """Cache de resultados + execucao unica por chave. Acertos nao gastam token nem cota."""
        if self._cache_results:
            hit = self._results.get(key)
            if hit is not None:
                self._record_hit(usage_key, model, client_id)
                return Reply(hit, cached=True, tokens=0, quota_remaining=self._remaining(client_id))

        def compute_and_store() -> _Outcome:
            outcome = compute()
            if self._cache_results and outcome.cacheable:
                self._results.set(key, outcome.text)
            return outcome

        try:
            outcome, leader = self._flight.do(key, compute_and_store)
        except TimeoutError as error:
            raise DiggerError("Uma análise idêntica está demorando demais. Tente novamente.") from error
        if leader:
            return Reply(outcome.text, tokens=outcome.tokens, quota_remaining=self._remaining(client_id))
        self._record_hit(usage_key, model, client_id)
        return Reply(outcome.text, cached=True, tokens=0, quota_remaining=self._remaining(client_id))

    # -- casos de uso ----------------------------------------------------------
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
        usage_key: str = "",
        reasoning_effort: str | None = None,
        requires: str | None = None,
    ) -> Reply:
        """`requires`: tema (ver extraction.CUE_KINDS) que o abstract precisa trazer; sem ele a analise e
        bloqueada sem chamar o modelo (zero token), em vez de deixar a IA preencher a lacuna."""
        filters = filters or Filters()
        key = _digest(
            "analyze", canonical_key(article_id), f"{build_fn.__module__}.{build_fn.__qualname__}", label,
            clinical, check_numbers, footer, filters.publico, filters.tom, filters.idioma, filters.detalhe,
            filters.foco, model, reasoning_effort, self._policy, requires,
        )

        def compute() -> _Outcome:
            if requires is None:
                self._generator.ensure_available(model)
                article = self._repository.get(article_id)
            else:
                article = self._repository.get(article_id)
                if not has_cues(article.abstract, requires):
                    return _Outcome(blocked_markdown(label, requires, article.title), tokens=0)
                self._generator.ensure_available(model)
            messages = build_fn(
                wrap_source("SOURCE_TITLE", article.title),
                wrap_source("SOURCE_ABSTRACT", article.abstract),
                sys_prompt=build_dynamic_sys_prompt(
                    filters.publico, filters.tom, filters.idioma, filters.detalhe, filters.foco
                ),
            )
            completion, tokens = self._run(
                messages, model, client_id, "Erro ao gerar resumo com a LLM", usage_key or label,
                self._options(filters.detalhe, reasoning_effort),
            )
            body = f"## Título do Artigo: {article.title}\n\n### Resumo:\n{completion.text}"
            if check_numbers:
                body += check_numeric_grounding(
                    completion.text, f"{article.title}\n{article.abstract}"
                ).to_markdown()
            if clinical:
                body += CLINICAL_DISCLAIMER
            if completion.truncated:
                body += TRUNCATION_NOTICE
            for warning in article.warnings:
                body += f"\n\n> 🛡️ **Aviso de segurança:** {warning}"
            return _Outcome(
                f"---\n> **{label}**  ·  Filtros: *{filters.describe()}*\n\n---\n{body}{footer}",
                tokens, cacheable=not completion.truncated,
            )

        return self._serve(key, client_id=client_id, model=model, usage_key=usage_key or label, compute=compute)

    def audit(
        self, article_id: str, model: str, response_text: str, *, client_id: str = "local", usage_key: str = "audit"
    ) -> Reply:
        """Auditoria de uma resposta anterior. Nao usa cache (depende do texto auditado)."""
        if not response_text:
            raise DiggerError("Gere uma análise antes de executar a auditoria.")
        article = self._repository.get(article_id)
        messages = build_message_auditoria_resposta(
            wrap_source("SOURCE_TITLE", article.title),
            wrap_source("SOURCE_ABSTRACT", article.abstract),
            response_text,
        )
        completion, tokens = self._run(
            messages, model, client_id, "Erro ao auditar a resposta", usage_key, self._options()
        )
        notice = TRUNCATION_NOTICE if completion.truncated else ""
        return Reply(
            f"---\n> **Auditoria da Resposta**\n\n---\n{completion.text}{notice}",
            tokens=tokens, quota_remaining=self._remaining(client_id),
        )

    def compare(
        self,
        article_id_a: str,
        article_id_b: str,
        analysis_type: str,
        model: str,
        *,
        medical_context: bool = False,
        client_id: str = "local",
        usage_key: str = "compare",
    ) -> Reply:
        if not (article_id_a or "").strip() or not (article_id_b or "").strip():
            raise DiggerError("Informe os dois IDs ou URLs para comparar os artigos.")
        key = _digest(
            "compare", canonical_key(article_id_a), canonical_key(article_id_b), analysis_type, model, medical_context,
            self._policy,
        )

        def compute() -> _Outcome:
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
            completion, tokens = self._run(
                messages, model, client_id, "Erro ao comparar os artigos", usage_key, self._options()
            )
            suffix = (CLINICAL_DISCLAIMER if medical_context else "") + (
                TRUNCATION_NOTICE if completion.truncated else ""
            )
            return _Outcome(
                f"---\n> **Comparação entre Artigos**\n\n---\n{completion.text}{suffix}",
                tokens, cacheable=not completion.truncated,
            )

        return self._serve(key, client_id=client_id, model=model, usage_key=usage_key, compute=compute)

    def _record_for(self, article_id: str) -> EuropePmcRecord | None:
        key = canonical_key(article_id)
        cached = self._records.get(key)
        if cached is not None:
            return cached[0]
        record = self._metadata_fetcher(article_id)
        if record is not None:  # falhas nao sao cacheadas: a proxima tentativa pode funcionar
            self._records.set(key, (record,))
        return record

    def extract(
        self,
        article_id: str,
        kind: str = "overview",
        *,
        label: str = "",
        client_id: str = "local",
        clinical: bool = False,
    ) -> Reply:
        """Extracao sem IA (zero token): resumo organizado, numeros com a frase de origem e metadados
        (`overview`) ou trechos copiados do abstract sobre um tema (`dose`, `conduta`, ...)."""
        if kind != "overview" and kind not in PASSAGE_KINDS:
            raise DiggerError("Tipo de extração inválido.")
        if not (article_id or "").strip():
            raise DiggerError("Cole um ID ou URL de artigo antes de extrair.")
        try:
            self._limiter.check(client_id)
        except RateLimitExceeded as error:
            raise RateLimitedError(str(error)) from error
        article = self._repository.get(article_id)
        if kind == "overview":
            markdown = overview_markdown(article.title, article.abstract, self._record_for(article_id))
        else:
            markdown = passages_markdown(label or kind, kind, article.title, article.abstract)
        if clinical:
            markdown += CLINICAL_EXTRACT_DISCLAIMER
        for warning in article.warnings:
            markdown += f"\n\n> 🛡️ **Aviso de segurança:** {warning}"
        return Reply(markdown, tokens=0, quota_remaining=self._remaining(client_id))

    def cite(self, article_id: str, style: str, *, client_id: str = "local") -> str:
        """Referencia formatada (ABNT/APA/Vancouver) a partir de registros oficiais, sem LLM."""
        if not (article_id or "").strip():
            raise DiggerError("Cole um DOI, PMID ou PMCID para gerar a referência.")
        try:
            self._limiter.check(client_id)
        except RateLimitExceeded as error:
            raise RateLimitedError(str(error)) from error
        meta = self._citation_fetcher(article_id)
        reference = citations.format_citation(meta, style)
        return (
            f"---\n> **Referência · {style}**\n\n---\n{reference}\n\n"
            "> Gerada automaticamente a partir do registro oficial (Crossref ou Europe PMC), "
            "sem uso de IA. Confira com as normas do seu curso antes de entregar."
        )
