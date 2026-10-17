"""Servico de descoberta: busca em catalogos, pagina do artigo e artigos semelhantes.

Nao usa IA nem gasta token: tudo vem dos registros das fontes e da extracao por codigo.
Busca e obras ficam em cache; cada identidade tem limite por minuto.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, replace

from loguru import logger

import article_services
import citations
import downloads
import reliability
from cache import TTLCache
from catalog import Catalog, CatalogError, SearchQuery, SearchResult, Work
from domain import ArticleNotFoundError, DiggerError, RateLimitedError, SourceUnavailableError
from enrichment import Enricher, Enrichment
from extraction import AbstractSection, Finding, extract_findings, split_sections
from ratelimit import RateLimitExceeded, SlidingWindowLimiter

SEARCH_CACHE_TTL = 600
WORK_CACHE_TTL = 3600
CACHE_SIZE = 512
SIMILAR_LIMIT = 6
MAX_SIMILAR_TERMS = 4
_TITLE_WORD = re.compile(r"[^\W\d_]{5,}", re.UNICODE)
_STOP_WORDS = frozenset(
    ["about", "after", "among", "between", "during", "their", "there", "these", "those", "which", "while", "with", "without", "using", "study", "studies", "analysis", "effect", "effects", "results", "result", "review", "based", "novel", "versus", "under", "through", "towards", "toward", "sobre", "entre", "durante", "desde", "estudo", "estudos", "analise", "efeito", "efeitos", "resultado", "resultados", "revisao", "baseado", "treatment", "therapy", "patients", "clinical", "report", "final", "tratamento", "terapia", "pacientes", "clinico", "relatorio"]
)
# termos MeSH de contexto que aparecem em quase todo artigo e estragam a busca por semelhantes
_GENERIC_KEYWORDS = frozenset([
    "humans", "human", "male", "female", "animals", "animal", "adult", "adults", "aged", "middle aged", "young adult",
    "adolescent", "child", "infant", "mice", "rats", "retrospective studies", "prospective studies", "cohort studies",
    "risk factors", "treatment outcome", "follow-up studies", "time factors",
])
ALL_SOURCES = "all"
ALL_SOURCES_NAME = "Todas as fontes"
ALL_DEADLINE = 14.0  # segundos; fonte mais lenta fica de fora desta busca (e entra no cache para a proxima)
MIN_PER_SOURCE = 2
_NON_WORD = re.compile(r"\W+")
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


def _identity_keys(work: Work) -> set[str]:
    keys = {f"doi:{work.doi.lower()}"} if work.doi else set()
    if work.pmid:
        keys.add(f"pmid:{work.pmid}")
    title = _NON_WORD.sub("", work.title.lower())
    if len(title) >= 25:  # titulo longo igual = mesma obra (inclui preprint e versao publicada)
        keys.add(f"title:{title}")
    return keys


def _richer(first: Work, second: Work) -> Work:
    """Entre dois registros do mesmo artigo, o que traz resumo e tipo de estudo oficial."""
    def score(work: Work) -> tuple[bool, bool]:
        return bool(work.abstract), bool(work.study_types)
    return second if score(second) > score(first) else first


def _merge(results: Sequence[SearchResult], query: SearchQuery) -> tuple[Work, ...]:
    """Junta resultados de varias fontes: intercala (relevancia) ou ordena (mais citados, mais recentes)."""
    interleaved: list[Work] = []
    for position in range(max(len(r.works) for r in results)):
        interleaved.extend(r.works[position] for r in results if position < len(r.works))
    unique: list[Work] = []
    seen: dict[str, int] = {}
    for work in interleaved:
        keys = _identity_keys(work)
        index = next((seen[k] for k in keys if k in seen), None)
        if index is None:
            index = len(unique)
            unique.append(work)
        else:
            unique[index] = _richer(unique[index], work)
        for k in keys:
            seen[k] = index
    if query.sort == "cited":
        unique.sort(key=lambda w: w.cited_by, reverse=True)
    elif query.sort == "recent":
        unique.sort(key=lambda w: w.year or 0, reverse=True)
    return tuple(unique)


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
        self._enricher = Enricher()
        self._fulltexts: TTLCache[downloads.FullText | bool] = TTLCache(64, WORK_CACHE_TTL)
        self._searches: TTLCache[SearchResult] = TTLCache(CACHE_SIZE, SEARCH_CACHE_TTL)
        self._works: TTLCache[Work] = TTLCache(CACHE_SIZE, WORK_CACHE_TTL)

    # -- catalogo ---------------------------------------------------------
    @property
    def default_source(self) -> str:
        return self._default

    @property
    def _combined(self) -> list[Catalog]:
        """Fontes que entram na busca combinada (as principais; as demais sao escolhidas uma a uma)."""
        return [c for c in self._catalogs.values() if getattr(c, "combined", True)]

    @property
    def search_default(self) -> str:
        """Fonte usada quando a busca nao escolhe uma: todas, se houver mais de uma fonte combinavel."""
        return ALL_SOURCES if len(self._combined) > 1 else self._default

    def sources(self) -> list[dict[str, object]]:
        combined = self._combined
        has_all = len(combined) > 1
        listed: list[dict[str, object]] = [
            {"id": c.id, "name": c.name, "studyTypes": list(c.study_types()), "default": c.id == self._default and not has_all}
            for c in self._catalogs.values()
        ]
        if has_all:
            union = list(dict.fromkeys(t for c in combined for t in c.study_types()))
            name = ALL_SOURCES_NAME if len(combined) == len(self._catalogs) else " + ".join(c.name.split(" (")[0] for c in combined)
            listed.insert(0, {"id": ALL_SOURCES, "name": name, "studyTypes": union, "default": True})
        return listed

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
        query = query.normalized()
        if source == ALL_SOURCES and len(self._combined) > 1:
            return self._search_all(query, client_id)
        catalog = self._catalog(source)
        if self._searches.get(repr((catalog.id, query))) is None:  # acertos de cache nao gastam o limite
            self._check(client_id)
        return self._search_one(catalog, query)

    def _search_one(self, catalog: Catalog, query: SearchQuery) -> SearchResult:
        key = repr((catalog.id, query))
        cached = self._searches.get(key)
        if cached is not None:
            return cached
        try:
            result = catalog.search(query)
        except CatalogError as error:
            raise SourceUnavailableError(str(error)) from error
        self._searches.set(key, result)
        for work in result.works:  # a pagina do artigo reaproveita o que a busca ja trouxe
            self._works.set(f"{catalog.id}:{work.ref}", work)
        return result

    def _search_all(self, query: SearchQuery, client_id: str) -> SearchResult:
        """Consulta todas as fontes em paralelo e junta: sem repetidos, intercalando por relevancia.

        O total e a soma dos totais de cada fonte (aproximado: o mesmo artigo pode estar em varias).
        Fonte que falha ou que nao oferece o filtro escolhido vira aviso; so falha se todas falharem.
        """
        key = repr((ALL_SOURCES, query))
        cached = self._searches.get(key)
        if cached is not None:
            return cached
        self._check(client_id)
        notes: list[str] = []
        runnable: list[tuple[Catalog, SearchQuery]] = []
        for catalog in self._combined:
            supported = set(catalog.study_types())
            wanted = tuple(t for t in query.study_types if t in supported)
            if query.study_types and not wanted:
                notes.append(f"{catalog.name.split(' (')[0]} não foi consultada: não oferece os tipos de estudo escolhidos.")
                continue
            runnable.append((catalog, replace(query, study_types=wanted)))
        if not runnable:
            raise SourceUnavailableError("Nenhuma fonte oferece os tipos de estudo escolhidos. Ajuste os filtros.")

        # cada fonte entrega uma fatia da pagina, para a pagina combinada ter o tamanho pedido
        per_source = max(MIN_PER_SOURCE, -(-query.per_page // len(runnable))) if len(runnable) > 1 else query.per_page
        runnable = [(catalog, replace(sub_query, per_page=per_source)) for catalog, sub_query in runnable]

        def run(item: tuple[Catalog, SearchQuery]) -> SearchResult | None:
            try:
                return self._search_one(item[0], item[1])
            except DiggerError as error:
                logger.debug("Fonte {} falhou na busca combinada: {}", item[0].id, error)
                return None

        pool = ThreadPoolExecutor(max_workers=len(runnable))
        futures = [(catalog, pool.submit(run, item)) for item in runnable for catalog in (item[0],)]
        wait([f for _, f in futures], timeout=ALL_DEADLINE)
        pool.shutdown(wait=False, cancel_futures=True)  # quem atrasou termina sozinho e deixa o resultado no cache
        results: list[SearchResult] = []
        for catalog, future in futures:
            short = catalog.name.split(" (")[0]
            if not future.done():
                notes.append(f"{short} demorou demais e ficou de fora desta busca; tente de novo em instantes.")
            elif future.result() is None:
                notes.append(f"{short} não respondeu; os resultados abaixo vêm das outras fontes.")
            else:
                results.append(future.result())  # type: ignore[arg-type]
        if not results:
            raise SourceUnavailableError("Nenhuma fonte de artigos respondeu agora. Tente novamente em instantes.")
        merged = SearchResult(
            works=_merge(results, query), total=sum(r.total for r in results), page=query.page,
            per_page=query.per_page, source=ALL_SOURCES, notes=tuple(notes),
        )
        self._searches.set(key, merged)
        return merged

    # -- obra -----------------------------------------------------------------
    def _find(self, ref: str, source: str | None) -> Work | None:
        source = None if source == ALL_SOURCES else source
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
        return self._analyze(work, ())  # os semelhantes carregam a parte, por rota propria

    def analysis(self, ref: str, *, client_id: str = "local") -> WorkDetail:
        """Mesma analise da pagina do artigo, sem artigos semelhantes (nao faz busca extra)."""
        return self._analyze(self.work(ref, client_id=client_id), ())

    def _analyze(self, work: Work, similar: tuple[Work, ...]) -> WorkDetail:
        sections = tuple(split_sections(work.abstract))
        findings = tuple(extract_findings(work.abstract))
        return WorkDetail(
            work=work,
            sections=sections,
            findings=findings,
            reliability=reliability.assess(work, sections, findings),
            citations={style: citations.format_citation(citation_metadata(work), style) for style in citations.FORMATTERS},
            similar=similar,
        )

    def enrich(self, ref: str, *, client_id: str = "local") -> Enrichment:
        """Registros de ensaio, citacoes e dados ligados ao artigo (fontes abertas, melhor esforco)."""
        work = self.work(ref, client_id=client_id)
        cached = self._enricher.cached(work)
        if cached is not None:
            return cached
        self._check(client_id)
        return self._enricher.enrich(work)

    def cached_enrichment(self, ref: str, *, client_id: str = "local") -> Enrichment | None:
        return self._enricher.cached(self.work(ref, client_id=client_id))

    def fulltext(self, ref: str, *, client_id: str = "local") -> downloads.FullText | None:
        """Texto completo aberto (Europe PMC, so PMC de acesso aberto); None quando nao existe. Resultado em cache."""
        work = self.work(ref, client_id=client_id)
        cached = self._fulltexts.get(work.ref)
        if cached is not None:
            return cached if isinstance(cached, downloads.FullText) else None
        self._check(client_id)
        pmcid = work.pmcid or self._pmcid_from_europepmc(work)
        result: downloads.FullText | None = None
        if pmcid:
            try:
                xml = downloads.fetch_fulltext_xml(pmcid)
            except CatalogError as error:
                raise SourceUnavailableError(str(error)) from error
            if xml is not None:
                try:
                    result = downloads.jats_to_fulltext(pmcid, xml)
                except CatalogError:
                    result = None
        self._fulltexts.set(work.ref, result or False)
        return result

    def _pmcid_from_europepmc(self, work: Work) -> str:
        catalog = self._catalogs.get("europepmc")
        key = work.pmid or work.doi
        if catalog is None or not key:
            return ""
        try:
            found = catalog.get(key)
        except CatalogError:
            return ""
        return found.pmcid if found else ""

    @staticmethod
    def similar_terms(work: Work) -> list[str]:
        """Termos que definem a semelhanca: palavras-chave do artigo ou, sem elas, as palavras mais longas do titulo."""
        keywords = [" ".join(re.sub(r"[,;]+", " ", k).split()) for k in work.keywords]
        keywords = [k for k in keywords if len(k) > 2 and k.lower() not in _GENERIC_KEYWORDS]
        words = [w for w in dict.fromkeys(_TITLE_WORD.findall(work.title.lower())) if w not in _STOP_WORDS]
        words.sort(key=len, reverse=True)
        chosen = keywords[:2]
        words = [w for w in words if not any(w in k.lower() for k in chosen)]  # nao repete o que ja esta numa palavra-chave
        mixed = chosen + words[:2] if keywords else words
        return list(dict.fromkeys(mixed))[:MAX_SIMILAR_TERMS]

    def similar(self, work: Work, *, client_id: str = "local") -> tuple[Work, ...]:
        """Artigos parecidos: busca pelos termos do artigo na mesma fonte, por relevancia. Falhas viram lista vazia."""
        terms = self.similar_terms(work)
        if not terms:
            return ()
        try:
            result = self.search(
                SearchQuery(q=" ".join(terms), sort="relevance", per_page=SIMILAR_LIMIT + 4),
                source=self._source_of(work), client_id=client_id,
            )
        except DiggerError:
            return ()
        own = {work.ref, work.pmid, work.doi, work.pmcid} - {""}
        own_title = _NON_WORD.sub("", work.title.lower())
        others = [
            w for w in result.works
            if not ({w.ref, w.pmid, w.doi, w.pmcid} - {""}) & own and _NON_WORD.sub("", w.title.lower()) != own_title
        ]
        return tuple(others[:SIMILAR_LIMIT])

    def _source_of(self, work: Work) -> str | None:
        """Catalogo que produziu a obra (o nome curto do catalogo e o `source` da obra)."""
        for catalog in self._catalogs.values():
            if work.source == catalog.name.split(" (")[0]:
                return catalog.id
        return None
