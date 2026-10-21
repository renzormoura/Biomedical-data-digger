"""Catalogo DOAJ: artigos de revistas de acesso aberto de todas as areas. Sem chave."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import requests
from loguru import logger

from catalog import CatalogError, SearchQuery, SearchResult, Work
from openalex_catalog import split_name

API_URL = "https://doaj.org/api/search/articles/"
HTTP_TIMEOUT = 20
USER_AGENT = "NexusScience/1.0 (navegador de artigos)"
_ES_SPECIAL = set('+-=&|!(){}[]^"~*?:\\/<>')
MAX_KEYWORDS = 12


def _terms(text: str) -> str:
    """Termos da busca sem operadores do Elasticsearch; palavras ligadas por AND."""
    cleaned = "".join(" " if ch in _ES_SPECIAL else ch for ch in text)
    words = [w for w in cleaned.split() if w.upper() not in {"AND", "OR", "NOT", "TO"}][:12]
    return " AND ".join(words)


def build_query(query: SearchQuery) -> str:
    base = _terms(query.q)
    if not base:
        return ""
    clauses = [f"({base})"]
    if query.year_from or query.year_to:
        clauses.append(f"bibjson.year:[{query.year_from or 1000} TO {query.year_to or 2100}]")
    if query.language:
        clauses.append(f"bibjson.journal.language:{query.language.upper()}")
    return " AND ".join(clauses)


def _identifier(bibjson: dict[str, Any], kind: str) -> str:
    return next((str(i.get("id") or "") for i in bibjson.get("identifier") or [] if i.get("type") == kind), "")


def to_work(record: dict[str, Any]) -> Work:
    bib = record.get("bibjson") or {}
    journal = bib.get("journal") or {}
    doi = _identifier(bib, "doi")
    year = str(bib.get("year") or "")
    start, end = str(bib.get("start_page") or ""), str(bib.get("end_page") or "")
    links = [str(link.get("url") or "") for link in bib.get("link") or [] if link.get("url")]
    languages = journal.get("language") or []
    return Work(
        ref=doi or f"doaj:{record.get('id', '')}",
        title=str(bib.get("title") or "Título não informado").strip(),
        authors=tuple(split_name(str(a.get("name") or "").strip()) for a in bib.get("author") or [] if a.get("name")),
        journal=str(journal.get("title") or ""),
        year=int(year) if year.isdigit() else None,
        volume=str(journal.get("volume") or ""),
        issue=str(journal.get("number") or ""),
        pages=f"{start}-{end}" if start and end and start != end else start,
        doi=doi,
        open_access=True,
        oa_url=links[0] if links else (f"https://doi.org/{doi}" if doi else ""),
        language=str(languages[0]).lower()[:2] if languages else "",
        abstract=str(bib.get("abstract") or "").strip(),
        keywords=tuple(dict.fromkeys(str(k) for k in bib.get("keywords") or []))[:MAX_KEYWORDS],
        source="DOAJ",
    )


class DoajCatalog:
    id = "doaj"
    name = "DOAJ (revistas de acesso aberto)"
    combined = True

    def study_types(self) -> tuple[str, ...]:
        return ()

    def _request(self, search: str, params: dict[str, str]) -> dict[str, Any]:
        try:
            response = requests.get(
                API_URL + quote(search, safe=""), params=params, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as error:
            logger.warning("DOAJ indisponivel: {}", error)
            raise CatalogError("A busca no DOAJ está indisponível agora. Tente novamente em instantes.") from error

    def search(self, query: SearchQuery) -> SearchResult:
        query = query.normalized()
        search = build_query(query)
        if not search:
            return SearchResult(works=(), total=0, page=query.page, per_page=query.per_page, source=self.id)
        data = self._request(search, {"page": str(query.page), "pageSize": str(query.per_page)})
        notes: tuple[str, ...] = ()
        if query.sort != "relevance":
            notes += ("O DOAJ não ordena por data nem por citações; os resultados seguem a relevância.",)
        if query.study_types:
            notes += ("O DOAJ não tem filtro de tipo de estudo; ele não foi aplicado.",)
        total = data.get("total")
        return SearchResult(
            works=tuple(to_work(r) for r in data.get("results") or []), total=total if isinstance(total, int) else 0,
            page=query.page, per_page=query.per_page, source=self.id, notes=notes,
        )

    def get(self, ref: str) -> Work | None:
        ref = ref.strip()
        if ref.startswith("10."):
            search = f"doi:{ref}"
        elif ref.startswith("doaj:") and ref[5:].isalnum():
            search = f"id:{ref[5:]}"
        else:
            return None
        data = self._request(search, {"pageSize": "1"})
        results = data.get("results") or []
        return to_work(results[0]) if results else None
