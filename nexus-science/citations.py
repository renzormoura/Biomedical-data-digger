"""Referencias bibliograficas ABNT, APA e Vancouver sem uso de LLM.

Os dados vem de registros oficiais (Crossref para DOI, Europe PMC para PMID/PMCID)
e a formatacao e codigo deterministico: nada e inventado. Campos ausentes no
registro sao omitidos da referencia, nunca preenchidos por suposicao.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import requests

import article_services
from domain import NexusError

HTTP_TIMEOUT = 15
USER_AGENT = {"User-Agent": "NexusScience/1.0"}


@dataclass(frozen=True)
class Author:
    family: str
    given: str = ""

    @property
    def initials(self) -> list[str]:
        parts = [part for part in re.split(r"[\s.\-]+", self.given) if part]
        return [part[0].upper() for part in parts]


@dataclass(frozen=True)
class CitationMetadata:
    title: str
    authors: tuple[Author, ...] = field(default_factory=tuple)
    journal: str = ""
    year: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    doi: str = ""


# ---------------------------------------------------------------------------
# Formatadores (puros)
# ---------------------------------------------------------------------------
def _clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", title)).strip().rstrip(".")


def _pages_dash(pages: str, dash: str) -> str:
    return re.sub(r"\s*[-–—]\s*", dash, pages.strip())


def format_abnt(meta: CitationMetadata) -> str:
    def name(author: Author) -> str:
        initials = " ".join(f"{i}." for i in author.initials)
        return f"{author.family.upper()}, {initials}".strip().rstrip(",")

    authors = list(meta.authors)
    if not authors:
        head = ""
    elif len(authors) > 3:
        head = f"{name(authors[0])} et al."
    else:
        head = "; ".join(name(a) for a in authors)
        if not head.endswith("."):
            head += "."
    parts = [head, f"{_clean_title(meta.title)}."] if head else [f"{_clean_title(meta.title).upper()}."]
    tail = [meta.journal]
    if meta.volume:
        tail.append(f"v. {meta.volume}")
    if meta.issue:
        tail.append(f"n. {meta.issue}")
    if meta.pages:
        tail.append(f"p. {_pages_dash(meta.pages, '-')}")
    if meta.year:
        tail.append(meta.year)
    journal_part = ", ".join(item for item in tail if item)
    if journal_part:
        parts.append(f"{journal_part}.")
    if meta.doi:
        parts.append(f"DOI: {meta.doi}.")
    return " ".join(part for part in parts if part)


def format_apa(meta: CitationMetadata) -> str:
    def name(author: Author) -> str:
        initials = " ".join(f"{i}." for i in author.initials)
        return f"{author.family}, {initials}".strip().rstrip(",")

    names = [name(a) for a in meta.authors[:20]]
    if not names:
        head = ""
    elif len(names) == 1:
        head = names[0]
    else:
        head = ", ".join(names[:-1]) + ", & " + names[-1]
    if len(meta.authors) > 20:
        head += ", et al."
    year = f"({meta.year})" if meta.year else "(s.d.)"
    lead = f"{head} {year}." if head else f"{_clean_title(meta.title)}. {year}."
    parts = [lead]
    if head:
        parts.append(f"{_clean_title(meta.title)}.")
    source = f"*{meta.journal}*" if meta.journal else ""
    if meta.volume:
        source += f", *{meta.volume}*"
        if meta.issue:
            source += f"({meta.issue})"
    if meta.pages:
        source += f", {_pages_dash(meta.pages, '–')}"
    if source:
        parts.append(f"{source}.")
    if meta.doi:
        parts.append(f"https://doi.org/{meta.doi}")
    return " ".join(parts)


def format_vancouver(meta: CitationMetadata) -> str:
    def name(author: Author) -> str:
        return f"{author.family} {''.join(author.initials)}".strip()

    authors = list(meta.authors)
    head = ", ".join(name(a) for a in authors[:6])
    if len(authors) > 6:
        head += ", et al"
    parts = [f"{head}." if head else "", f"{_clean_title(meta.title)}."]
    publication = meta.journal
    if publication:
        publication += "."
    locator = meta.year
    if meta.volume:
        locator += f";{meta.volume}"
        if meta.issue:
            locator += f"({meta.issue})"
    if meta.pages:
        locator += f":{_pages_dash(meta.pages, '-')}"
    if publication:
        parts.append(publication)
    if locator:
        parts.append(f"{locator}.")
    if meta.doi:
        parts.append(f"doi:{meta.doi}")
    return " ".join(part for part in parts if part)


def _join_and(names: list[str], conjunction: str) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + f", {conjunction} " + names[-1] if len(names) > 2 else f"{names[0]} {conjunction} {names[1]}"


def format_ieee(meta: CitationMetadata) -> str:
    """IEEE: iniciais antes do sobrenome; mais de seis autores vira "Primeiro et al."."""
    def name(author: Author) -> str:
        initials = " ".join(f"{i}." for i in author.initials)
        return f"{initials} {author.family}".strip()

    authors = list(meta.authors)
    head = f"{name(authors[0])} et al." if len(authors) > 6 else _join_and([name(a) for a in authors], "and")
    parts = [head + "," if head else "", f"\"{_clean_title(meta.title)},\""]
    source = [f"*{meta.journal}*" if meta.journal else ""]
    if meta.volume:
        source.append(f"vol. {meta.volume}")
    if meta.issue:
        source.append(f"no. {meta.issue}")
    if meta.pages:
        source.append(f"pp. {_pages_dash(meta.pages, '–')}" if re.search(r"[-–—]", meta.pages) else f"p. {meta.pages.strip()}")
    if meta.year:
        source.append(meta.year)
    if meta.doi:
        source.append(f"doi: {meta.doi}")
    tail = ", ".join(item for item in source if item)
    if tail:
        parts.append(tail + ".")
    else:
        parts[-1] = parts[-1][:-2] + '."'
    return " ".join(part for part in parts if part)


def format_harvard(meta: CitationMetadata) -> str:
    """Harvard (autor-data): Sobrenome, A.B., Sobrenome, C. and Sobrenome, D. (2020) 'Titulo', Revista, 1(2), pp. 3-4."""
    def name(author: Author) -> str:
        return f"{author.family}, {''.join(f'{i}.' for i in author.initials)}".strip().rstrip(",")

    authors = list(meta.authors)
    head = f"{name(authors[0])} et al." if len(authors) > 3 else _join_and([name(a) for a in authors], "and").replace(", and ", " and ")
    year = f"({meta.year})" if meta.year else "(n.d.)"
    lead = f"{head} {year}" if head else f"'{_clean_title(meta.title)}' {year}"
    parts = [lead + (f" '{_clean_title(meta.title)}'," if head else ".")]
    source = f"*{meta.journal}*" if meta.journal else ""
    if meta.volume:
        source += f", {meta.volume}" if source else meta.volume
        if meta.issue:
            source += f"({meta.issue})"
    if meta.pages:
        label = "pp." if re.search(r"[-–—]", meta.pages) else "p."
        source += f", {label} {_pages_dash(meta.pages, '–')}" if source else f"{label} {_pages_dash(meta.pages, '–')}"
    if source:
        parts.append(f"{source}.")
    elif head:
        parts[0] = parts[0].rstrip(",") + "."
    if meta.doi:
        parts.append(f"doi:{meta.doi}.")
    return " ".join(parts)


def format_mla(meta: CitationMetadata) -> str:
    """MLA 9: Sobrenome, Nome, e Nome Sobrenome. "Titulo." Revista, vol. 1, no. 2, 2020, pp. 3-4, doi."""
    authors = list(meta.authors)

    def inverted(author: Author) -> str:
        return f"{author.family}, {author.given}".strip().rstrip(",")

    if not authors:
        head = ""
    elif len(authors) == 1:
        head = inverted(authors[0]) + "."
    elif len(authors) == 2:
        head = f"{inverted(authors[0])}, and {authors[1].given} {authors[1].family}.".replace("  ", " ")
    else:
        head = f"{inverted(authors[0])}, et al."
    parts = [head, f"\"{_clean_title(meta.title)}.\""]
    source = [f"*{meta.journal}*" if meta.journal else ""]
    if meta.volume:
        source.append(f"vol. {meta.volume}")
    if meta.issue:
        source.append(f"no. {meta.issue}")
    if meta.year:
        source.append(meta.year)
    if meta.pages:
        source.append(f"pp. {_pages_dash(meta.pages, '-')}" if re.search(r"[-–—]", meta.pages) else f"p. {meta.pages.strip()}")
    if meta.doi:
        source.append(f"https://doi.org/{meta.doi}")
    tail = ", ".join(item for item in source if item)
    if tail:
        parts.append(tail + ".")
    return " ".join(part for part in parts if part)


FORMATTERS: dict[str, Callable[[CitationMetadata], str]] = {
    "ABNT": format_abnt,
    "APA": format_apa,
    "Vancouver": format_vancouver,
    "IEEE": format_ieee,
    "Harvard": format_harvard,
    "MLA": format_mla,
}


def format_citation(meta: CitationMetadata, style: str) -> str:
    try:
        return FORMATTERS[style](meta)
    except KeyError as error:
        raise NexusError(f"Estilo de citação desconhecido: {style}.") from error


# ---------------------------------------------------------------------------
# Coleta de metadados (rede)
# ---------------------------------------------------------------------------
def _first(value: Any) -> str:
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value or "")


def parse_crossref(message: dict[str, Any]) -> CitationMetadata:
    authors = tuple(
        Author(family=a.get("family", ""), given=a.get("given", ""))
        for a in message.get("author", [])
        if a.get("family")
    )
    issued = (message.get("issued", {}).get("date-parts") or [[None]])[0]
    year = str(issued[0]) if issued and issued[0] else ""
    return CitationMetadata(
        title=_first(message.get("title")),
        authors=authors,
        journal=_first(message.get("container-title")),
        year=year,
        volume=str(message.get("volume", "") or ""),
        issue=str(message.get("issue", "") or ""),
        pages=str(message.get("page", "") or ""),
        doi=str(message.get("DOI", "") or ""),
    )


def parse_europe_pmc(record: dict[str, Any]) -> CitationMetadata:
    raw_authors = (record.get("authorList") or {}).get("author", [])
    authors = tuple(
        Author(family=a.get("lastName", ""), given=a.get("firstName") or a.get("initials", ""))
        for a in raw_authors
        if a.get("lastName")
    )
    journal_info = record.get("journalInfo") or {}
    journal = (journal_info.get("journal") or {}).get("title") or record.get("journalTitle", "")
    return CitationMetadata(
        title=record.get("title", ""),
        authors=authors,
        journal=journal or "",
        year=str(record.get("pubYear") or journal_info.get("yearOfPublication") or ""),
        volume=str(journal_info.get("volume") or ""),
        issue=str(journal_info.get("issue") or ""),
        pages=str(record.get("pageInfo") or ""),
        doi=str(record.get("doi") or ""),
    )


def _get_json(url: str, **kwargs: Any) -> dict[str, Any]:
    try:
        response = requests.get(url, timeout=HTTP_TIMEOUT, headers=USER_AGENT, **kwargs)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as error:
        raise NexusError(f"Não foi possível consultar a fonte de metadados: {error}") from error


def fetch_citation_metadata(raw: str) -> CitationMetadata:
    """Resolve DOI, PMID ou PMCID em metadados; outros formatos pedem um DOI/PMID."""
    input_type, value = article_services.detect_input_type(raw.strip())
    if input_type == "doi":
        data = _get_json(f"https://api.crossref.org/works/{value}")
        meta = parse_crossref(data.get("message", {}))
    elif input_type in ("pmid", "pmcid"):
        field_name = "EXT_ID" if input_type == "pmid" else "PMCID"
        data = _get_json(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            params={"query": f"{field_name}:{value}", "resultType": "core", "format": "json"},
        )
        results = (data.get("resultList") or {}).get("result", [])
        if not results:
            raise NexusError("Artigo não encontrado na Europe PMC.")
        meta = parse_europe_pmc(results[0])
    else:
        raise NexusError("Para gerar referências, informe um DOI, PMID ou PMCID.")
    if not meta.title:
        raise NexusError("O registro encontrado não tem título; não é possível gerar a referência.")
    return meta
