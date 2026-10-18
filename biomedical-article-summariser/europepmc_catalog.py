"""Catalogo Europe PMC: busca com filtros, ordenacao, paginacao e tipo de estudo oficial.

Fonte padrao do navegador: gratuita, sem chave e sem orcamento diario por IP, e devolve numa
unica chamada o resumo, autores, volume/paginas, identificadores, acesso aberto (com link),
tipo de publicacao e citacoes. Cobre ciencias da vida e da saude.
"""

from __future__ import annotations

import html
import re
from typing import Any

import requests
from loguru import logger

import article_services
from catalog import ISO2_TO_ISO3, CatalogError, SearchQuery, SearchResult, Work, iso2, iso_date
from citations import Author
from extraction import STUDY_TYPE_LABELS, study_type_labels

SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
HTTP_TIMEOUT = 20
MAX_KEYWORDS = 12

# Filtro (rotulo em portugues) -> tipo de publicacao da Europe PMC.
STUDY_FILTERS: dict[str, str] = {
    "Ensaio clínico randomizado": "Randomized Controlled Trial",
    "Ensaio clínico": "Clinical Trial",
    "Meta-análise": "Meta-Analysis",
    "Revisão sistemática": "Systematic Review",
    "Revisão": "Review",
    "Relato de caso": "Case Reports",
    "Estudo observacional": "Observational Study",
    "Estudo multicêntrico": "Multicenter Study",
    "Diretriz de prática clínica": "Practice Guideline",
}
SORT_PARAMS = {"relevance": None, "cited": "CITED desc", "recent": "P_PDATE_D desc"}

_KNOWN_LABELS = frozenset(STUDY_TYPE_LABELS.values())
_TAG = re.compile(r"<[^>]+>")
_H4 = re.compile(r"<h4[^>]*>\s*(.*?)\s*</h4>", re.IGNORECASE | re.DOTALL)


def clean_html_text(text: str) -> str:
    """Texto simples a partir de HTML da Europe PMC; cabecalhos <h4> viram "Rotulo: "."""
    text = _H4.sub(lambda m: f" {_TAG.sub('', m.group(1)).strip().rstrip(':')}: ", text or "")
    text = re.sub(r"</(?:p|div|li|h\d)>|<br\s*/?>", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub("", text))).strip()


def _clean_title(raw: str) -> str:
    """Titulo sem HTML, sem ponto final e sem os colchetes que a Europe PMC poe em titulos traduzidos."""
    title = clean_html_text(raw).rstrip(".").strip()
    if title.startswith("[") and title.endswith("]"):
        title = title[1:-1].strip()
    return title


def _escape_user_text(text: str) -> str:
    cleaned = text.replace("\\", " ")
    if cleaned.count('"') % 2:  # aspas desbalanceadas quebram a consulta
        cleaned = cleaned.replace('"', " ")
    return cleaned.strip()


def build_query(query: SearchQuery) -> str:
    """Monta a consulta da Europe PMC (sintaxe de campos) a partir dos filtros."""
    text = _escape_user_text(query.q)
    parts = [f"({text})" if text else "HAS_ABSTRACT:y"]
    if query.year_from or query.year_to:
        parts.append(f"PUB_YEAR:[{query.year_from or 1800} TO {query.year_to or 2100}]")
    if query.open_access:
        parts.append("OPEN_ACCESS:y")
    types = [STUDY_FILTERS[t] for t in query.study_types if t in STUDY_FILTERS]
    if types:
        parts.append("(" + " OR ".join(f'PUB_TYPE:"{t}"' for t in types) + ")")
    if query.language in ISO2_TO_ISO3:
        parts.append(f"LANG:{ISO2_TO_ISO3[query.language]}")
    return " AND ".join(parts)


def _authors(record: dict[str, Any]) -> tuple[Author, ...]:
    entries = (record.get("authorList") or {}).get("author") or []
    authors = []
    for entry in entries:
        family = entry.get("lastName") or ""
        given = entry.get("firstName") or entry.get("initials") or ""
        if not family and entry.get("fullName"):
            family, _, given = entry["fullName"].partition(" ")
        if family:
            authors.append(Author(family=family, given=given))
    if authors:
        return tuple(authors)
    # alternativa: "Depommier C, Everard A."
    names = [n.strip() for n in (record.get("authorString") or "").rstrip(".").split(",") if n.strip()]
    return tuple(Author(family=n.rsplit(" ", 1)[0], given=n.rsplit(" ", 1)[-1]) if " " in n else Author(family=n) for n in names)


def _oa_url(record: dict[str, Any]) -> str:
    urls = ((record.get("fullTextUrlList") or {}).get("fullTextUrl")) or []
    free = [u for u in urls if u.get("availabilityCode") in ("OA", "F") and str(u.get("url", "")).startswith("http")]
    free.sort(key=lambda u: 0 if u.get("documentStyle") == "html" else 1)
    return free[0]["url"] if free else ""


def _keywords(record: dict[str, Any]) -> tuple[str, ...]:
    keywords = [str(k) for k in ((record.get("keywordList") or {}).get("keyword")) or []]
    if not keywords:
        keywords = [
            str(m["descriptorName"]) for m in ((record.get("meshHeadingList") or {}).get("meshHeading")) or []
            if isinstance(m, dict) and m.get("descriptorName")
        ]
    return tuple(dict.fromkeys(keywords))[:MAX_KEYWORDS]


def _int(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, str)) and str(value).isdigit() else None


def to_work(record: dict[str, Any]) -> Work:
    """Converte um resultado `core` da Europe PMC em `Work`."""
    pmid = str(record.get("pmid") or "")
    pmcid = str(record.get("pmcid") or "")
    doi = str(record.get("doi") or "")
    info = record.get("journalInfo") or {}
    pub_types = [str(t) for t in (record.get("pubTypeList") or {}).get("pubType") or []]
    study_types = [label for label in study_type_labels(pub_types) if label in _KNOWN_LABELS]
    if record.get("source") == "PPR" and "Preprint" not in study_types:
        study_types.append("Preprint")
    return Work(
        ref=pmid or pmcid or doi or str(record.get("id") or ""),
        title=_clean_title(str(record.get("title") or "Título não informado")),
        authors=_authors(record),
        journal=str((info.get("journal") or {}).get("title") or record.get("journalTitle") or ""),
        year=_int(record.get("pubYear")),
        published=iso_date(record.get("firstPublicationDate")),
        volume=str(info.get("volume") or ""),
        issue=str(info.get("issue") or ""),
        pages=str(record.get("pageInfo") or ""),
        doi=doi,
        pmid=pmid,
        pmcid=pmcid,
        # na navegacao so entram rotulos que sabemos traduzir; tipos tecnicos do registro virariam ruido
        study_types=tuple(study_types),
        open_access=record.get("isOpenAccess") == "Y",
        oa_url=_oa_url(record),
        cited_by=_int(record.get("citedByCount")) or 0,
        language=iso2(str(record.get("language") or "")),
        abstract=clean_html_text(str(record.get("abstractText") or "")),
        keywords=_keywords(record),
        source="Europe PMC",
        retracted="retracted publication" in {t.lower() for t in pub_types},
    )


class EuropePmcCatalog:
    id = "europepmc"
    name = "Europe PMC (ciências da vida e saúde)"

    def study_types(self) -> tuple[str, ...]:
        return tuple(STUDY_FILTERS)

    def _request(self, params: dict[str, str]) -> dict[str, Any]:
        try:
            response = requests.get(SEARCH_URL, params={**params, "format": "json"}, timeout=HTTP_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as error:
            logger.warning("Europe PMC indisponivel: {}", error)
            raise CatalogError("A busca na Europe PMC está indisponível agora. Tente novamente em instantes.") from error

    def search(self, query: SearchQuery) -> SearchResult:
        query = query.normalized()
        params = {
            "query": build_query(query), "resultType": "core",
            "pageSize": str(query.per_page), "page": str(query.page),
        }
        sort = SORT_PARAMS[query.sort]
        if sort:
            params["sort"] = sort
        data = self._request(params)
        records = (data.get("resultList") or {}).get("result") or []
        return SearchResult(
            works=tuple(to_work(r) for r in records),
            total=_int(data.get("hitCount")) or 0,
            page=query.page,
            per_page=query.per_page,
            source=self.id,
        )

    def get(self, ref: str) -> Work | None:
        input_type, value = article_services.detect_input_type(ref.strip())
        field = {"pmid": f"EXT_ID:{value} AND SRC:MED", "pmcid": f"PMCID:{value}", "doi": f'DOI:"{value}"'}.get(input_type)
        if field is None:
            return None
        data = self._request({"query": field, "resultType": "core", "pageSize": "1"})
        records = (data.get("resultList") or {}).get("result") or []
        return to_work(records[0]) if records else None
