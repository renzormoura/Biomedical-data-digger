"""Catalogo OpenAlex: todas as areas do conhecimento (opcional, exige chave de API).

Sem chave, o OpenAlex divide um orcamento diario minusculo por IP (inviavel em hospedagem
compartilhada), entao o adaptador so e ativado quando `OPENALEX_API_KEY` esta configurada.
Diferente da Europa PMC, nao informa o delineamento do estudo (RCT, coorte...), apenas o tipo
da obra (artigo, revisao, preprint...), entao o filtro "tipo" aqui e mais grosseiro.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import requests
from loguru import logger

from article_services import _abstract_from_inverted_index
from catalog import CatalogError, SearchQuery, SearchResult, Work, iso2, iso_date
from citations import Author

BASE_URL = "https://api.openalex.org/works"
HTTP_TIMEOUT = 20
MAX_KEYWORDS = 12
SELECT = (
    "id,doi,title,display_name,publication_year,publication_date,type,language,cited_by_count,open_access,primary_location,"
    "authorships,biblio,abstract_inverted_index,keywords,topics,ids"
)

# Filtro (rotulo em portugues) -> tipo de obra do OpenAlex.
TYPE_FILTERS: dict[str, str] = {
    "Artigo": "article",
    "Revisão": "review",
    "Preprint": "preprint",
    "Capítulo de livro": "book-chapter",
    "Dissertação": "dissertation",
}
_TYPE_LABELS = {value: label for label, value in TYPE_FILTERS.items()} | {"book": "Livro", "dataset": "Conjunto de dados"}
SORT_PARAMS = {"relevance": None, "cited": "cited_by_count:desc", "recent": "publication_date:desc"}
_PARTICLES = frozenset({"de", "da", "do", "dos", "das", "van", "von", "der", "den", "di", "del", "della", "la", "le", "el"})


def split_name(display_name: str) -> Author:
    """Separa "Nome Sobrenome" em given/family (heuristica: ultimo termo, com particulas)."""
    tokens = display_name.split()
    if len(tokens) < 2:
        return Author(family=display_name.strip())
    cut = len(tokens) - 1
    while cut > 1 and tokens[cut - 1].lower() in _PARTICLES:
        cut -= 1
    return Author(family=" ".join(tokens[cut:]), given=" ".join(tokens[:cut]))


def _short_id(url: str) -> str:
    return url.rsplit("/", 1)[-1] if url else ""


def to_work(record: dict[str, Any]) -> Work:
    ids = record.get("ids") or {}
    doi = str(record.get("doi") or "").removeprefix("https://doi.org/")
    pmid = _short_id(str(ids.get("pmid") or ""))
    work_id = _short_id(str(record.get("id") or ""))
    location = record.get("primary_location") or {}
    biblio = record.get("biblio") or {}
    first, last = biblio.get("first_page"), biblio.get("last_page")
    open_access = record.get("open_access") or {}
    keywords = [str(k.get("display_name")) for k in record.get("keywords") or [] if k.get("display_name")]
    if not keywords:
        keywords = [str(t.get("display_name")) for t in record.get("topics") or [] if t.get("display_name")]
    authors = tuple(
        split_name(str((a.get("author") or {}).get("display_name") or "").strip())
        for a in record.get("authorships") or []
        if (a.get("author") or {}).get("display_name")
    )
    work_type = _TYPE_LABELS.get(str(record.get("type") or ""), "")
    cited = record.get("cited_by_count")
    year = record.get("publication_year")
    return Work(
        ref=pmid or doi or work_id,
        title=str(record.get("title") or record.get("display_name") or "Título não informado").strip(),
        authors=authors,
        journal=str((location.get("source") or {}).get("display_name") or ""),
        year=year if isinstance(year, int) else None,
        published=iso_date(record.get("publication_date")),
        volume=str(biblio.get("volume") or ""),
        issue=str(biblio.get("issue") or ""),
        pages=f"{first}-{last}" if first and last and first != last else str(first or ""),
        doi=doi,
        pmid=pmid,
        study_types=(work_type,) if work_type else (),
        open_access=bool(open_access.get("is_oa")),
        oa_url=str(open_access.get("oa_url") or ""),
        cited_by=cited if isinstance(cited, int) else 0,
        language=iso2(str(record.get("language") or "")),
        abstract=_abstract_from_inverted_index(record.get("abstract_inverted_index")),
        keywords=tuple(dict.fromkeys(keywords))[:MAX_KEYWORDS],
        source="OpenAlex",
        retracted=record.get("is_retracted") is True,
    )


def _filter_value(text: str) -> str:
    """Virgula e barra vertical separam filtros no OpenAlex; tiram-se do valor."""
    return " ".join(text.replace(",", " ").replace("|", " ").split())


def build_filter(query: SearchQuery) -> str:
    parts = []
    if query.q and _filter_value(query.q):
        # restringe o casamento a titulo e resumo (so "search" casa com o texto completo e traz obras fora do tema)
        parts.append(f"title_and_abstract.search:{_filter_value(query.q)}")
    if query.year_from or query.year_to:
        parts.append(f"publication_year:{query.year_from or 1800}-{query.year_to or 2100}")
    if query.open_access:
        parts.append("open_access.is_oa:true")
    types = [TYPE_FILTERS[t] for t in query.study_types if t in TYPE_FILTERS]
    if types:
        parts.append("type:" + "|".join(types))
    if query.language:
        parts.append(f"language:{query.language}")
    return ",".join(parts)


class OpenAlexCatalog:
    id = "openalex"
    name = "OpenAlex (todas as áreas)"

    def __init__(self, api_key: str, mailto: str = "") -> None:
        if not api_key:
            raise ValueError("OpenAlexCatalog exige uma chave de API.")
        self._api_key = api_key
        self._mailto = mailto

    def study_types(self) -> tuple[str, ...]:
        return tuple(TYPE_FILTERS)

    def _request(self, url: str, params: dict[str, str]) -> dict[str, Any] | None:
        params = {**params, "api_key": self._api_key}
        if self._mailto:
            params["mailto"] = self._mailto
        try:
            response = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
        except requests.RequestException as error:
            logger.warning("OpenAlex indisponivel: {}", type(error).__name__)
            raise CatalogError("A busca no OpenAlex está indisponível agora. Tente a Europe PMC.") from error
        if response.status_code == 404:
            return None
        if response.status_code in (402, 403, 429):
            logger.warning("OpenAlex recusou a chamada (status {}): limite ou chave", response.status_code)
            raise CatalogError("O OpenAlex atingiu o limite de uso. Tente a Europe PMC ou volte mais tarde.")
        try:
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as error:
            logger.warning("OpenAlex respondeu com erro: {}", type(error).__name__)
            raise CatalogError("A busca no OpenAlex falhou. Tente a Europe PMC.") from error

    def search(self, query: SearchQuery) -> SearchResult:
        query = query.normalized()
        params = {"select": SELECT, "per-page": str(query.per_page), "page": str(query.page)}
        if query.q:
            params["search"] = query.q
        filters = build_filter(query)
        if filters:
            params["filter"] = filters
        sort = SORT_PARAMS[query.sort]
        if sort:
            params["sort"] = sort
        data = self._request(BASE_URL, params) or {}
        meta = data.get("meta") or {}
        return SearchResult(
            works=tuple(to_work(r) for r in data.get("results") or []),
            total=int(meta.get("count") or 0),
            page=query.page,
            per_page=query.per_page,
            source=self.id,
        )

    def get(self, ref: str) -> Work | None:
        ref = ref.strip()
        if ref.upper().startswith("W") and ref[1:].isdigit():
            key = ref.upper()
        elif ref.isdigit():
            key = f"pmid:{ref}"
        elif ref.lower().startswith("10."):
            key = f"doi:{ref}"
        else:
            return None
        data = self._request(f"{BASE_URL}/{quote(key, safe=':')}", {"select": SELECT})
        return to_work(data) if data else None
