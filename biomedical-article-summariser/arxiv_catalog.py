"""Catalogo arXiv: preprints de computacao, inteligencia artificial, fisica e matematica.

Sem chave. Os termos de uso pedem no maximo uma requisicao a cada 3 segundos por IP, entao as
chamadas passam por um espacador global. Todo o conteudo e aberto (PDF no proprio arXiv); os
registros entram como "Preprint", sem revisao por pares.
"""

from __future__ import annotations

import re
import threading
import time
from xml.etree.ElementTree import Element

import requests
from loguru import logger

from catalog import CatalogError, SearchQuery, SearchResult, Work, iso_date
from openalex_catalog import split_name
from xmlutil import parse_xml, text_of

API_URL = "https://export.arxiv.org/api/query"
HTTP_TIMEOUT = 25
MIN_INTERVAL = 3.0
USER_AGENT = "BiomedicalDataDigger/1.0 (navegador de artigos)"
NS = {
    "a": "http://www.w3.org/2005/Atom",
    "o": "http://a9.com/-/spec/opensearch/1.1/",
    "x": "http://arxiv.org/schemas/atom",
}
_TOKEN = re.compile(r"[\w-]+", re.UNICODE)
_ID = re.compile(r"^(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?$")
_VERSION = re.compile(r"v\d+$")
_LAST_CALL = 0.0
_LOCK = threading.Lock()


def _throttle() -> None:
    """Garante o intervalo minimo entre chamadas ao arXiv, no processo inteiro."""
    global _LAST_CALL
    with _LOCK:
        wait = MIN_INTERVAL - (time.monotonic() - _LAST_CALL)
        if wait > 0:
            time.sleep(wait)
        _LAST_CALL = time.monotonic()


def build_search(query: SearchQuery) -> str:
    """`all:termo AND all:termo [AND submittedDate:[...]]`; so letras, numeros e hifen entram na consulta."""
    tokens = _TOKEN.findall(query.q)[:12]
    if not tokens:
        return ""
    clauses = [f"all:{token}" for token in tokens]
    if query.year_from or query.year_to:
        start, end = query.year_from or 1991, query.year_to or 2100
        clauses.append(f"submittedDate:[{start}01010000 TO {end}12312359]")
    return " AND ".join(clauses)


def _first(entry: Element, path: str) -> Element | None:
    return entry.find(path, NS)


def to_work(entry: Element) -> Work:
    raw_id = text_of(_first(entry, "a:id"))
    arxiv_id = _VERSION.sub("", raw_id.rsplit("/abs/", 1)[-1])
    published = text_of(_first(entry, "a:published"))
    pdf = next((link.get("href", "") for link in entry.findall("a:link", NS) if link.get("title") == "pdf"), "")
    return Work(
        ref=arxiv_id,
        title=text_of(_first(entry, "a:title")) or "Título não informado",
        authors=tuple(split_name(text_of(a)) for a in entry.findall("a:author/a:name", NS) if text_of(a)),
        journal=text_of(_first(entry, "x:journal_ref")) or "arXiv (preprint)",
        year=int(published[:4]) if published[:4].isdigit() else None,
        published=iso_date(published),
        doi=text_of(_first(entry, "x:doi")),
        study_types=("Preprint",),
        open_access=True,
        oa_url=pdf or f"https://arxiv.org/abs/{arxiv_id}",
        language="en",
        abstract=text_of(_first(entry, "a:summary")),
        source="arXiv",
    )


class ArxivCatalog:
    id = "arxiv"
    name = "arXiv (computação, física e matemática)"
    combined = True

    def study_types(self) -> tuple[str, ...]:
        return ()

    def _request(self, params: dict[str, str]) -> Element:
        _throttle()
        try:
            response = requests.get(API_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as error:
            logger.warning("arXiv indisponivel: {}", error)
            raise CatalogError("A busca no arXiv está indisponível agora. Tente novamente em instantes.") from error
        return parse_xml(response.content)

    def search(self, query: SearchQuery) -> SearchResult:
        query = query.normalized()
        search = build_search(query)
        if not search:
            return SearchResult(works=(), total=0, page=query.page, per_page=query.per_page, source=self.id)
        params = {
            "search_query": search, "start": str((query.page - 1) * query.per_page), "max_results": str(query.per_page),
            "sortBy": "submittedDate" if query.sort == "recent" else "relevance", "sortOrder": "descending",
        }
        root = self._request(params)
        total = text_of(root.find("o:totalResults", NS))
        notes: tuple[str, ...] = (
            ("O arXiv não ordena por citações; os resultados seguem a relevância.",) if query.sort == "cited" else ()
        )
        if query.open_access or query.study_types or query.language:
            notes += ("O arXiv não tem esses filtros (acesso aberto, tipo de estudo, idioma); eles não foram aplicados.",)
        return SearchResult(
            works=tuple(to_work(e) for e in root.findall("a:entry", NS)), total=int(total) if total.isdigit() else 0,
            page=query.page, per_page=query.per_page, source=self.id, notes=notes,
        )

    def get(self, ref: str) -> Work | None:
        candidate = ref.strip().removeprefix("arXiv:").removeprefix("arxiv:")
        if not _ID.match(candidate):
            return None
        root = self._request({"id_list": _VERSION.sub("", candidate), "max_results": "1"})
        entries = root.findall("a:entry", NS)
        if not entries or "Error" in text_of(entries[0].find("a:title", NS)):
            return None
        return to_work(entries[0])
