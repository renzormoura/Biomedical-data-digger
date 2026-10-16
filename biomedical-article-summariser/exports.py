"""Exportacao da biblioteca em BibTeX, RIS e texto ABNT (sem IA, so os metadados do registro)."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

import citations
from catalog import Work
from discovery import citation_metadata

_BIB_SPECIAL = re.compile(r"([&%#_$])")


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def _bib(value: str) -> str:
    return _BIB_SPECIAL.sub(r"\\\1", value)


def _clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", title)).strip().rstrip(".")


def _pages(pages: str, dash: str) -> str:
    return re.sub(r"\s*[-–—]\s*", dash, pages.strip(), count=1)


def _bib_key(work: Work, used: set[str]) -> str:
    family = re.sub(r"[^a-z0-9]", "", _ascii(work.authors[0].family)) if work.authors else "anon"
    word = next(iter(re.findall(r"[a-z]{4,}", _ascii(work.title))), "artigo")
    key = f"{family}{work.year or ''}{word}"
    while key in used:
        key += "x"
    used.add(key)
    return key


def to_bibtex(works: Sequence[Work]) -> str:
    used: set[str] = set()
    entries = []
    for work in works:
        fields = [
            ("author", " and ".join(f"{_bib(a.family)}, {_bib(a.given)}".rstrip(", ") for a in work.authors)),
            ("title", "{" + _bib(_clean_title(work.title)) + "}"),
            ("journal", _bib(work.journal)),
            ("year", str(work.year or "")),
            ("volume", work.volume),
            ("number", work.issue),
            ("pages", _pages(work.pages, "--") if work.pages else ""),
            ("doi", work.doi),
        ]
        body = ",\n".join(f"  {name} = {{{value}}}" for name, value in fields if value)
        entries.append(f"@article{{{_bib_key(work, used)},\n{body}\n}}")
    return "\n\n".join(entries)


def to_ris(works: Sequence[Work]) -> str:
    records = []
    for work in works:
        lines = ["TY  - JOUR", *(f"AU  - {a.family}, {a.given}".rstrip(", ") for a in work.authors)]
        lines.append(f"TI  - {_clean_title(work.title)}")
        if work.journal:
            lines.append(f"JO  - {work.journal}")
        if work.year:
            lines.append(f"PY  - {work.year}")
        if work.volume:
            lines.append(f"VL  - {work.volume}")
        if work.issue:
            lines.append(f"IS  - {work.issue}")
        if work.pages:
            start, _, end = re.sub(r"\s*[-–—]\s*", "-", work.pages).partition("-")
            lines.append(f"SP  - {start}")
            if end:
                lines.append(f"EP  - {end}")
        if work.doi:
            lines.append(f"DO  - {work.doi}")
        lines.extend(f"KW  - {keyword}" for keyword in work.keywords)
        if work.abstract:
            lines.append(f"AB  - {work.abstract}")
        lines.append("ER  - ")
        records.append("\n".join(lines))
    return "\n\n".join(records)


def to_citations(works: Sequence[Work], style: str = "ABNT") -> str:
    return "\n\n".join(citations.format_citation(citation_metadata(w), style) for w in works)


EXPORT_FORMATS = {
    "bibtex": ("biblioteca.bib", "application/x-bibtex", to_bibtex),
    "ris": ("biblioteca.ris", "application/x-research-info-systems", to_ris),
    "abnt": ("referencias-abnt.txt", "text/plain", lambda works: to_citations(works, "ABNT")),
    "apa": ("referencias-apa.txt", "text/plain", lambda works: to_citations(works, "APA")),
    "vancouver": ("referencias-vancouver.txt", "text/plain", lambda works: to_citations(works, "Vancouver")),
}
