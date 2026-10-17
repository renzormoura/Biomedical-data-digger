"""Enriquecimento do artigo com fontes abertas, sem chave e sem IA.

- ClinicalTrials.gov: confirma os registros de ensaio (NCT) citados no resumo;
- OpenCitations: contagem de citacoes por DOI;
- DataCite (cobre Zenodo, figshare e outros): dados, codigos e materiais ligados ao DOI do artigo.

Tudo e melhor esforco: cada fonte falha sozinha e vira "sem dados", nunca derruba a pagina do artigo.
As consultas rodam em paralelo, com prazo curto, e o resultado fica em cache por artigo.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import requests
from loguru import logger

from cache import TTLCache
from catalog import Work

HTTP_TIMEOUT = 12
_FAILED = object()  # a fonte nao respondeu (diferente de "respondeu e nao ha dados")
CACHE_TTL = 3600
CACHE_SIZE = 512
USER_AGENT = "BiomedicalDataDigger/1.0 (navegador de artigos)"
MAX_TRIALS = 3
MAX_RELATED = 5
_NCT = re.compile(r"\bNCT\d{8}\b")
_DOI = re.compile(r"^10\.\d{4,9}/\S+$")
_DATA_KINDS = frozenset({"Dataset", "Software", "Collection", "Image", "Audiovisual", "Workflow", "Model", "Text"})
STATUS_LABELS = {
    "COMPLETED": "Concluído", "RECRUITING": "Recrutando", "ACTIVE_NOT_RECRUITING": "Ativo, sem recrutar",
    "NOT_YET_RECRUITING": "Ainda não recrutando", "TERMINATED": "Encerrado", "WITHDRAWN": "Retirado",
    "SUSPENDED": "Suspenso", "ENROLLING_BY_INVITATION": "Recrutando por convite", "UNKNOWN": "Situação desconhecida",
}


@dataclass(frozen=True)
class Trial:
    nct: str
    title: str
    status: str
    start: str
    has_results: bool

    @property
    def url(self) -> str:
        return f"https://clinicaltrials.gov/study/{self.nct}"


@dataclass(frozen=True)
class RelatedData:
    doi: str
    title: str
    kind: str
    publisher: str

    @property
    def url(self) -> str:
        return f"https://doi.org/{self.doi}"


@dataclass(frozen=True)
class Enrichment:
    mentioned_trials: tuple[str, ...] = ()  # NCT citados no resumo
    trials: tuple[Trial, ...] = ()  # os que o registro confirmou
    citations: int | None = None
    related_data: tuple[RelatedData, ...] = ()


def mentioned_trials(work: Work) -> tuple[str, ...]:
    found = dict.fromkeys(_NCT.findall(f"{work.title} {work.abstract}"))
    return tuple(found)[:MAX_TRIALS]


def _get_json(url: str, params: dict[str, str] | None = None) -> Any:
    response = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def fetch_trial(nct: str) -> Trial | None:
    data = _get_json(
        f"https://clinicaltrials.gov/api/v2/studies/{nct}",
        {"fields": "NCTId|BriefTitle|OverallStatus|StartDate|HasResults"},
    )
    if not isinstance(data, dict):
        return None
    protocol = data.get("protocolSection") or {}
    status = str((protocol.get("statusModule") or {}).get("overallStatus") or "UNKNOWN")
    return Trial(
        nct=nct,
        title=str((protocol.get("identificationModule") or {}).get("briefTitle") or nct),
        status=STATUS_LABELS.get(status, status.replace("_", " ").capitalize()),
        start=str(((protocol.get("statusModule") or {}).get("startDateStruct") or {}).get("date") or ""),
        has_results=data.get("hasResults") is True,
    )


def fetch_citations(doi: str) -> int | None:
    data = _get_json(f"https://opencitations.net/index/api/v2/citation-count/doi:{doi}")
    if isinstance(data, list) and data:
        count = str(data[0].get("count", ""))
        return int(count) if count.isdigit() else None
    return None


def fetch_related_data(doi: str) -> tuple[RelatedData, ...]:
    data = _get_json(
        "https://api.datacite.org/dois",
        {"query": f'relatedIdentifiers.relatedIdentifier:"{doi}"', "page[size]": "25"},
    )
    related: list[RelatedData] = []
    for item in (data or {}).get("data") or []:
        attrs = item.get("attributes") or {}
        kind = str((attrs.get("types") or {}).get("resourceTypeGeneral") or "")
        item_doi = str(attrs.get("doi") or "")
        titles = attrs.get("titles") or []
        if kind in _DATA_KINDS and _DOI.match(item_doi) and titles:
            related.append(RelatedData(item_doi, str(titles[0].get("title") or item_doi), kind, str(attrs.get("publisher") or "")))
        if len(related) >= MAX_RELATED:
            break
    return tuple(related)


def _safe(label: str, func: Any, *args: Any) -> Any:
    try:
        return func(*args)
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        logger.debug("Enriquecimento {} falhou: {}", label, error)
        return _FAILED


class Enricher:
    def __init__(self) -> None:
        self._cache: TTLCache[Enrichment] = TTLCache(CACHE_SIZE, CACHE_TTL)

    def cached(self, work: Work) -> Enrichment | None:
        return self._cache.get(work.ref)

    def enrich(self, work: Work) -> Enrichment:
        cached = self._cache.get(work.ref)
        if cached is not None:
            return cached
        ncts = mentioned_trials(work)
        doi = work.doi if _DOI.match(work.doi or "") else ""
        with ThreadPoolExecutor(max_workers=4) as pool:
            trial_futures = [pool.submit(_safe, "trial", fetch_trial, n) for n in ncts]
            citations = pool.submit(_safe, "citations", fetch_citations, doi) if doi else None
            related = pool.submit(_safe, "datacite", fetch_related_data, doi) if doi else None
            outcomes = [f.result() for f in trial_futures]
            cited = citations.result() if citations else None
            data = related.result() if related else ()
        failed = _FAILED in (*outcomes, cited, data)
        result = Enrichment(
            mentioned_trials=ncts,
            trials=tuple(t for t in outcomes if isinstance(t, Trial)),
            citations=cited if isinstance(cited, int) else None,
            related_data=data if isinstance(data, tuple) else (),
        )
        if not failed:  # falha momentanea nao fica em cache: a proxima visita tenta de novo
            self._cache.set(work.ref, result)
        return result
