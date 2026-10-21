"""Catalogo OpenAIRE: publicacoes de pesquisa financiada, com ligacao a dados e projetos. Sem chave."""

from __future__ import annotations

import re
from typing import Any

import requests
from loguru import logger

from catalog import CatalogError, SearchQuery, SearchResult, Work, iso2, iso_date
from citations import Author

API_URL = "https://api.openaire.eu/graph/v1/researchProducts"
HTTP_TIMEOUT = 25
USER_AGENT = "NexusScience/1.0 (navegador de artigos)"
SORTS = {"relevance": None, "recent": "publicationDate DESC", "cited": "citationCount DESC"}
_TAG = re.compile(r"<[^>]+>")
_BLOCK_TAG = re.compile(r"</?(?:p|br|div|li|ul|ol|h\d|tr|td)\b[^>]*>", re.IGNORECASE)
_BAD_SEARCH = re.compile(r"[\"\\]")
_PID = re.compile(r"^(?:10\.\d{4,9}/\S+|PMC\d+|\d{1,9})$")


def _pid(record: dict[str, Any], scheme: str) -> str:
    return next((str(p.get("value") or "") for p in record.get("pids") or [] if p.get("scheme") == scheme), "")


def _clean(text: str) -> str:
    """Texto simples: tags de bloco viram espaco e as de linha (<i>, <b>) somem sem separar palavras."""
    return " ".join(_TAG.sub("", _BLOCK_TAG.sub(" ", text)).split())


def _first_url(record: dict[str, Any]) -> str:
    for instance in record.get("instances") or []:
        for url in instance.get("urls") or []:
            if isinstance(url, str) and url.startswith(("https://", "http://")):
                return url
    return ""


def to_work(record: dict[str, Any]) -> Work:
    doi, pmid, pmcid = _pid(record, "doi"), _pid(record, "pmid"), _pid(record, "pmc")
    date = str(record.get("publicationDate") or "")
    container = record.get("container") or {}
    start, end = str(container.get("sp") or ""), str(container.get("ep") or "")
    descriptions = record.get("descriptions") or []
    impact = (record.get("indicators") or {}).get("citationImpact") or {}
    cited = impact.get("citationCount")
    open_access = (record.get("bestAccessRight") or {}).get("label") == "OPEN"
    language = (record.get("language") or {}).get("code") or ""
    return Work(
        ref=pmid or doi or str(record.get("id") or ""),
        title=_clean(str(record.get("mainTitle") or "Título não informado")),
        authors=tuple(
            Author(family=str(a.get("surname") or ""), given=str(a.get("name") or ""))
            for a in record.get("authors") or [] if a.get("surname")
        ),
        journal=str(container.get("name") or ""),
        year=int(date[:4]) if date[:4].isdigit() else None,
        published=iso_date(date),
        volume=str(container.get("vol") or ""),
        issue=str(container.get("iss") or ""),
        pages=f"{start}-{end}" if start and end and start != end else start,
        doi=doi, pmid=pmid, pmcid=pmcid,
        open_access=open_access,
        oa_url=_first_url(record) if open_access else "",
        cited_by=int(cited) if isinstance(cited, (int, float)) else 0,
        language=iso2(str(language)),
        abstract=_clean(str(descriptions[0])) if descriptions else "",
        source="OpenAIRE",
    )


class OpenAireCatalog:
    id = "openaire"
    name = "OpenAIRE (pesquisa europeia)"
    combined = True

    def study_types(self) -> tuple[str, ...]:
        return ()

    def _request(self, params: dict[str, str]) -> dict[str, Any]:
        try:
            response = requests.get(API_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as error:
            logger.warning("OpenAIRE indisponivel: {}", error)
            raise CatalogError("A busca no OpenAIRE está indisponível agora. Tente novamente em instantes.") from error

    def search(self, query: SearchQuery) -> SearchResult:
        query = query.normalized()
        text = " ".join(_BAD_SEARCH.sub(" ", query.q).split())
        if not text:
            return SearchResult(works=(), total=0, page=query.page, per_page=query.per_page, source=self.id)
        params = {"search": text, "type": "publication", "page": str(query.page), "pageSize": str(query.per_page)}
        if SORTS[query.sort]:
            params["sortBy"] = SORTS[query.sort] or ""
        if query.year_from:
            params["fromPublicationDate"] = f"{query.year_from}-01-01"
        if query.year_to:
            params["toPublicationDate"] = f"{query.year_to}-12-31"
        data = self._request(params)
        notes: tuple[str, ...] = ()
        if query.open_access or query.study_types or query.language:
            notes = ("O OpenAIRE não tem esses filtros (acesso aberto, tipo de estudo, idioma); eles não foram aplicados.",)
        total = (data.get("header") or {}).get("numFound")
        return SearchResult(
            works=tuple(to_work(r) for r in data.get("results") or []), total=total if isinstance(total, int) else 0,
            page=query.page, per_page=query.per_page, source=self.id, notes=notes,
        )

    def get(self, ref: str) -> Work | None:
        ref = ref.strip()
        if not _PID.match(ref):
            return None
        data = self._request({"pid": ref, "pageSize": "1"})
        results = data.get("results") or []
        return to_work(results[0]) if results else None
