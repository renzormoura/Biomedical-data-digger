"""Servico de descoberta: busca em catalogos, pagina do artigo e artigos semelhantes.

Nao usa IA nem gasta token: tudo vem dos registros das fontes e da extracao por codigo.
Busca e obras ficam em cache; cada identidade tem limite por minuto.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from loguru import logger

import article_services
import citations
import reliability
from cache import TTLCache
from catalog import Catalog, CatalogError, SearchQuery, SearchResult, Work
from domain import ArticleNotFoundError, DiggerError, RateLimitedError, SourceUnavailableError
from extraction import AbstractSection, Finding, extract_findings, split_sections
from ratelimit import RateLimitExceeded, SlidingWindowLimiter

SEARCH_CACHE_TTL = 600
WORK_CACHE_TTL = 3600
CACHE_SIZE = 512
SIMILAR_LIMIT = 4
Fallback = Callable[[str], Work | None]


@dataclass(frozen=True)
class WorkDetail:
    work: Work
    sections: tuple[AbstractSection, ...]
    findings: tuple[Finding, ...]
    citations: Mapping[str, str]
    similar: tuple[Work, ...]
    reliability: reliability.Reliability


def citation_metadata(work: Work) -> citations.CitationMetadata:
    return citations.CitationMetadata(
        title=work.title,
        authors=work.authors,
        journal=work.journal,
        year=str(work.year or ""),
        volume=work.volume,
        issue=work.issue,
        pages=work.pages,
        doi=work.doi,
    )


def default_fallback(ref: str) -> Work | None:
    """Ultimo recurso: resolve por Crossref/Semantic Scholar/arXiv (so titulo e resumo)."""
    try:
        title, abstract, source = article_services.resolve_article(ref)
    except Exception as error:
        logger.debug("Fallback de resolucao falhou para {}: {}", ref, error)
        return None
    if not abstract:
        return None
    return Work(ref=ref, title=title, abstract=abstract, source=source)


class DiscoveryService:
    def __init__(
        self,
        catalogs: Sequence[Catalog],
        limiter: SlidingWindowLimiter,
        fallback: Fallback | None = default_fallback,
    ) -> None:
        if not catalogs:
            raise ValueError("Informe ao menos um catalogo.")
        self._catalogs = {catalog.id: catalog for catalog in catalogs}
        self._default = catalogs[0].id
        self._limiter = limiter
        self._fallback = fallback
        self._searches: TTLCache[SearchResult] = TTLCache(CACHE_SIZE, SEARCH_CACHE_TTL)
        self._works: TTLCache[Work] = TTLCache(CACHE_SIZE, WORK_CACHE_TTL)

    # -- catalogo ---------------------------------------------------------
    @property
    def default_source(self) -> str:
        return self._default

    def sources(self) -> list[dict[str, object]]:
        return [
            {"id": c.id, "name": c.name, "studyTypes": list(c.study_types()), "default": c.id == self._default}
            for c in self._catalogs.values()
        ]

    def _catalog(self, source: str | None) -> Catalog:
        catalog = self._catalogs.get(source or self._default)
        if catalog is None:
            raise DiggerError("Fonte de busca desconhecida.")
        return catalog

    def _check(self, client_id: str) -> None:
        try:
            self._limiter.check(client_id)
        except RateLimitExceeded as error:
            raise RateLimitedError(str(error)) from error

    # -- busca --------------------------------------------------------------
    def search(self, query: SearchQuery, *, source: str | None = None, client_id: str = "local") -> SearchResult:
        catalog = self._catalog(source)
        query = query.normalized()
        key = repr((catalog.id, query))
        cached = self._searches.get(key)
        if cached is not None:  # acertos de cache nao gastam o limite
            return cached
        self._check(client_id)
        try:
            result = catalog.search(query)
        except CatalogError as error:
            raise SourceUnavailableError(str(error)) from error
        self._searches.set(key, result)
        for work in result.works:  # a pagina do artigo reaproveita o que a busca ja trouxe
            self._works.set(f"{catalog.id}:{work.ref}", work)
        return result

    # -- obra -----------------------------------------------------------------
    def _find(self, ref: str, source: str | None) -> Work | None:
        ordered = [self._catalog(source)] if source else list(self._catalogs.values())
        errors = 0
        for catalog in ordered:
            cached = self._works.get(f"{catalog.id}:{ref}")
            if cached is not None:
                return cached
            try:
                work = catalog.get(ref)
            except CatalogError:
                errors += 1
                continue
            if work is not None:
                self._works.set(f"{catalog.id}:{ref}", work)
                return work
        if errors == len(ordered) and not self._fallback:
            raise SourceUnavailableError("As fontes de artigos estão indisponíveis agora. Tente novamente em instantes.")
        return None

    def work(self, ref: str, *, source: str | None = None, client_id: str = "local") -> Work:
        ref = (ref or "").strip()[:300]
        if not ref:
            raise DiggerError("Informe o identificador do artigo.")
        cached = [self._works.get(f"{c.id}:{ref}") for c in self._catalogs.values()]
        found = next((w for w in cached if w is not None), None)
        if found is not None:
            return found
        self._check(client_id)
        work = self._find(ref, source)
        if work is None and self._fallback is not None:
            work = self._fallback(ref)
            if work is not None:
                self._works.set(f"fallback:{ref}", work)
        if work is None:
            raise ArticleNotFoundError("Não encontramos este artigo nas fontes consultadas.")
        return work

    def detail(self, ref: str, *, source: str | None = None, client_id: str = "local") -> WorkDetail:
        work = self.work(ref, source=source, client_id=client_id)
        sections = tuple(split_sections(work.abstract))
        findings = tuple(extract_findings(work.abstract))
        return WorkDetail(
            work=work,
            sections=sections,
            findings=findings,
            reliability=reliability.assess(work, sections, findings),
            citations={style: citations.format_citation(citation_metadata(work), style) for style in citations.FORMATTERS},
            similar=self.similar(work, client_id=client_id),
        )

    def similar(self, work: Work, *, client_id: str = "local") -> tuple[Work, ...]:
        """Obras com as mesmas palavras-chave, mais citadas primeiro. Melhor esforco: falhas viram lista vazia."""
        terms = [k for k in work.keywords if k][:2]
        if not terms:
            return ()
        try:
            result = self.search(
                SearchQuery(q=" ".join(terms), sort="cited", per_page=SIMILAR_LIMIT + 2),
                source=self._source_of(work), client_id=client_id,
            )
        except DiggerError:
            return ()
        own = {work.ref, work.pmid, work.doi, work.pmcid} - {""}
        others = [w for w in result.works if not ({w.ref, w.pmid, w.doi, w.pmcid} - {""}) & own]
        return tuple(others[:SIMILAR_LIMIT])

    def _source_of(self, work: Work) -> str | None:
        """Catalogo que produziu a obra (o nome curto do catalogo e o `source` da obra)."""
        for catalog in self._catalogs.values():
            if work.source == catalog.name.split(" (")[0]:
                return catalog.id
        return None
