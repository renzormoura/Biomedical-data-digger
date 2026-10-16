"""Metadados oficiais da Europe PMC (tipo de publicacao, palavras-chave, financiamento).

Usado so para mostrar rotulos do registro, nunca para opinar. A consulta e "melhor esforco":
qualquer falha de rede ou formato devolve `None` e a interface segue sem esses campos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests
from loguru import logger

import article_services

SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
HTTP_TIMEOUT = 15
MAX_KEYWORDS = 12
MAX_GRANTS = 6


@dataclass(frozen=True)
class EuropePmcRecord:
    pub_types: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    mesh_terms: tuple[str, ...] = ()
    funders: tuple[str, ...] = ()
    open_access: bool | None = None
    cited_by: int | None = None
    journal: str = ""
    year: str = ""
    language: str = ""
    extra: dict[str, Any] = field(default_factory=dict, compare=False)


def _listing(container: Any, key: str) -> list[Any]:
    value = (container or {}).get(key, [])
    return value if isinstance(value, list) else [value]


def parse_record(result: dict[str, Any]) -> EuropePmcRecord:
    pub_types = [str(t) for t in _listing(result.get("pubTypeList"), "pubType")]
    keywords = [str(k) for k in _listing(result.get("keywordList"), "keyword")][:MAX_KEYWORDS]
    mesh = [
        str(m.get("descriptorName"))
        for m in _listing(result.get("meshHeadingList"), "meshHeading")
        if isinstance(m, dict) and m.get("descriptorName")
    ][:MAX_KEYWORDS]
    funders: list[str] = []
    for grant in _listing(result.get("grantsList"), "grant"):
        agency = grant.get("agency") if isinstance(grant, dict) else None
        if agency and agency not in funders:
            funders.append(str(agency))
    open_flag = result.get("isOpenAccess")
    cited = result.get("citedByCount")
    return EuropePmcRecord(
        pub_types=tuple(pub_types),
        keywords=tuple(keywords),
        mesh_terms=tuple(mesh),
        funders=tuple(funders[:MAX_GRANTS]),
        open_access={"Y": True, "N": False}.get(open_flag) if isinstance(open_flag, str) else None,
        cited_by=int(cited) if isinstance(cited, (int, str)) and str(cited).isdigit() else None,
        journal=str(result.get("journalTitle") or (result.get("journalInfo") or {}).get("journal", {}).get("title", "")),
        year=str(result.get("pubYear") or ""),
        language=str(result.get("language") or ""),
    )


def _query_for(raw: str) -> str | None:
    input_type, value = article_services.detect_input_type(raw.strip())
    if input_type == "pmid":
        return f"EXT_ID:{value} AND SRC:MED"
    if input_type == "pmcid":
        return f"PMCID:{value}"
    if input_type == "doi":
        return f'DOI:"{value}"'
    return None


def fetch_record(raw: str) -> EuropePmcRecord | None:
    """Registro da Europe PMC para PMID, PMCID ou DOI; `None` se nao houver ou se a consulta falhar."""
    query = _query_for(raw)
    if query is None:
        return None
    try:
        response = requests.get(
            SEARCH_URL,
            params={"query": query, "resultType": "core", "format": "json", "pageSize": "1"},
            timeout=HTTP_TIMEOUT,
        )
        response.raise_for_status()
        results = (response.json().get("resultList") or {}).get("result", [])
    except (requests.RequestException, ValueError) as error:
        logger.debug("Europe PMC indisponivel para metadados: {}", error)
        return None
    return parse_record(results[0]) if results else None
