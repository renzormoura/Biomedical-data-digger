"""Exportacao em BibTeX, RIS, EndNote, CSL JSON e estilos de citacao (sem IA, so os metadados do registro).

RIS importa no Zotero, Mendeley e EndNote; CSL JSON, no Zotero e no Pandoc; o formato .enw, no EndNote.
"""

from __future__ import annotations

import csv
import io
import json
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


def _url(work: Work) -> str:
    if work.doi:
        return f"https://doi.org/{work.doi}"
    if work.pmid:
        return f"https://pubmed.ncbi.nlm.nih.gov/{work.pmid}/"
    return ""


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
            ("url", _url(work)),
            ("pmid", work.pmid),
            ("keywords", ", ".join(_bib(k) for k in work.keywords)),
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
            lines.append(f"JF  - {work.journal}")
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
        if _url(work):
            lines.append(f"UR  - {_url(work)}")
        if work.pmid:
            lines.append(f"AN  - PMID:{work.pmid}")
        if work.language:
            lines.append(f"LA  - {work.language}")
        lines.extend(f"KW  - {keyword}" for keyword in work.keywords)
        if work.abstract:
            lines.append(f"AB  - {' '.join(work.abstract.split())}")
        lines.append("ER  - ")
        records.append("\n".join(lines))
    return "\n\n".join(records)


def to_endnote(works: Sequence[Work]) -> str:
    """EndNote "Refer" (.enw): importa no EndNote por Arquivo > Importar, com o filtro "EndNote Import"."""
    records = []
    for work in works:
        lines = ["%0 Journal Article", *(f"%A {a.family}, {a.given}".rstrip(", ") for a in work.authors)]
        lines.append(f"%T {_clean_title(work.title)}")
        for tag, value in (("%J", work.journal), ("%D", str(work.year or "")), ("%V", work.volume), ("%N", work.issue),
                           ("%P", _pages(work.pages, "-")), ("%R", work.doi), ("%U", _url(work)), ("%G", work.language),
                           ("%M", f"PMID:{work.pmid}" if work.pmid else "")):
            if value:
                lines.append(f"{tag} {value}")
        lines.extend(f"%K {keyword}" for keyword in work.keywords)
        if work.abstract:
            lines.append(f"%X {' '.join(work.abstract.split())}")
        records.append("\n".join(lines))
    return "\n\n".join(records) + "\n"


def _date_parts(work: Work) -> list[int]:
    if work.published:
        parts = [int(p) for p in work.published.split("-") if p.isdigit()]
        if parts and work.year and parts[0] == work.year:
            return parts[:3]
    return [work.year] if work.year else []


def to_csl_json(works: Sequence[Work]) -> str:
    """CSL JSON (Zotero, Mendeley, Pandoc e a maioria dos gerenciadores): uma lista de itens `article-journal`."""
    used: set[str] = set()
    items = []
    for work in works:
        item: dict[str, object] = {"id": _bib_key(work, used), "type": "article-journal", "title": _clean_title(work.title)}
        if work.authors:
            item["author"] = [{"family": a.family, "given": a.given} if a.given else {"family": a.family} for a in work.authors]
        for field, value in (
            ("container-title", work.journal), ("volume", work.volume), ("issue", work.issue), ("page", _pages(work.pages, "-")),
            ("DOI", work.doi), ("PMID", work.pmid), ("PMCID", work.pmcid), ("URL", _url(work)), ("language", work.language),
            ("abstract", " ".join(work.abstract.split())), ("keyword", ", ".join(work.keywords)),
        ):
            if value:
                item[field] = value
        if _date_parts(work):
            item["issued"] = {"date-parts": [_date_parts(work)]}
        items.append(item)
    return json.dumps(items, ensure_ascii=False, indent=2)


def to_citations(works: Sequence[Work], style: str = "ABNT") -> str:
    return "\n\n".join(citations.format_citation(citation_metadata(w), style) for w in works)


_CSV_COLUMNS = (
    ("titulo", lambda w: w.title), ("autores", lambda w: "; ".join(f"{a.family}, {a.given}".rstrip(", ") for a in w.authors)),
    ("periodico", lambda w: w.journal), ("ano", lambda w: str(w.year or "")), ("volume", lambda w: w.volume),
    ("numero", lambda w: w.issue), ("paginas", lambda w: w.pages), ("doi", lambda w: w.doi), ("pmid", lambda w: w.pmid),
    ("pmcid", lambda w: w.pmcid), ("tipo_de_estudo", lambda w: "; ".join(w.study_types)),
    ("acesso_aberto", lambda w: "sim" if w.open_access else "nao"), ("link_aberto", lambda w: w.oa_url),
    ("fonte", lambda w: w.source), ("citacoes", lambda w: str(w.cited_by)), ("resumo", lambda w: w.abstract),
)


def _csv_cell(value: str) -> str:
    """Planilhas executam celulas que comecam com = + - @; o apostrofo as torna texto."""
    value = value.replace("\r", " ").replace("\n", " ")
    return "'" + value if value[:1] in {"=", "+", "-", "@", "\t"} else value


def to_csv(works: Sequence[Work]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow([name for name, _ in _CSV_COLUMNS])
    for work in works:
        writer.writerow([_csv_cell(getter(work)) for _, getter in _CSV_COLUMNS])
    return "\ufeff" + out.getvalue()  # BOM: o Excel abre os acentos corretamente


def to_json(works: Sequence[Work]) -> str:
    return json.dumps([w.to_dict() for w in works], ensure_ascii=False, indent=2)


def to_abstracts(works: Sequence[Work]) -> str:
    """Todos os resumos em um unico Markdown, cada artigo com titulo, identificacao e o resumo original."""
    parts = ["# Resumos\n"]
    for work in works:
        ids = " · ".join(p for p in [f"https://doi.org/{work.doi}" if work.doi else "", f"PMID {work.pmid}" if work.pmid else ""] if p)
        authors = ", ".join(f"{a.given} {a.family}".strip() for a in work.authors[:6]) + (" et al." if len(work.authors) > 6 else "")
        parts.append(f"## {_clean_title(work.title)}\n\n{authors} · {work.journal} · {work.year or ''}  \n{ids}\n\n{work.abstract or 'Sem resumo no registro.'}\n")
    return "\n".join(parts)


EXPORT_FORMATS = {
    "bibtex": ("biblioteca.bib", "application/x-bibtex", to_bibtex),
    "ris": ("biblioteca.ris", "application/x-research-info-systems", to_ris),
    "endnote": ("biblioteca.enw", "application/x-endnote-refer", to_endnote),
    "csljson": ("biblioteca-csl.json", "application/vnd.citationstyles.csl+json", to_csl_json),
    "abnt": ("referencias-abnt.txt", "text/plain", lambda works: to_citations(works, "ABNT")),
    "apa": ("referencias-apa.txt", "text/plain", lambda works: to_citations(works, "APA")),
    "vancouver": ("referencias-vancouver.txt", "text/plain", lambda works: to_citations(works, "Vancouver")),
    "ieee": ("referencias-ieee.txt", "text/plain", lambda works: to_citations(works, "IEEE")),
    "harvard": ("referencias-harvard.txt", "text/plain", lambda works: to_citations(works, "Harvard")),
    "mla": ("referencias-mla.txt", "text/plain", lambda works: to_citations(works, "MLA")),
    "csv": ("biblioteca.csv", "text/csv", to_csv),
    "json": ("biblioteca.json", "application/json", to_json),
    "resumos": ("resumos.md", "text/markdown", to_abstracts),
}
