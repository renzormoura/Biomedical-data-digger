"""Catalogo PubMed (NCBI E-utilities): MEDLINE direto da fonte oficial.

Cada busca faz duas chamadas (esearch para os identificadores e efetch para os registros). Sem chave
o limite do NCBI e de 3 requisicoes por segundo; `NCBI_API_KEY` (opcional) eleva isso. Resumos
estruturados chegam com os rotulos originais (Background, Methods...), que a pagina do artigo usa.
"""

from __future__ import annotations

import re
from typing import Any
from xml.etree.ElementTree import Element

import requests
from loguru import logger

from catalog import ISO2_TO_ISO3, CatalogError, SearchQuery, SearchResult, Work, iso2
from citations import Author
from europepmc_catalog import STUDY_FILTERS
from extraction import STUDY_TYPE_LABELS, study_type_labels
from xmlutil import parse_xml, text_of

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
HTTP_TIMEOUT = 25
USER_AGENT = "BiomedicalDataDigger/1.0 (navegador de artigos)"
MAX_KEYWORDS = 12
_KNOWN_LABELS = frozenset(STUDY_TYPE_LABELS.values())
_UNSAFE = re.compile(r"[\[\]\"\\]")
_DIGITS = re.compile(r"\d{4}")
_PMC = re.compile(r"^PMC\d+$")
_DOI = re.compile(r"^10\.\d{4,9}/\S+$")


def build_term(query: SearchQuery) -> str:
    text = " ".join(_UNSAFE.sub(" ", query.q).split())
    if not text:
        return ""
    clauses = [f"({text})"]
    if query.year_from or query.year_to:
        clauses.append(f'("{query.year_from or 1000}"[dp] : "{query.year_to or 3000}"[dp])')
    if query.open_access:
        clauses.append("free full text[sb]")
    if query.language and query.language in ISO2_TO_ISO3:
        clauses.append(f"{ISO2_TO_ISO3[query.language]}[la]")
    types = [STUDY_FILTERS[t] for t in query.study_types if t in STUDY_FILTERS]
    if types:
        clauses.append("(" + " OR ".join(f'"{t}"[pt]' for t in types) + ")")
    return " AND ".join(clauses)


def _article_ids(article: Element) -> dict[str, str]:
    return {i.get("IdType", ""): text_of(i) for i in article.findall("PubmedData/ArticleIdList/ArticleId")}


def _abstract(article: Element) -> str:
    parts = []
    for node in article.findall("MedlineCitation/Article/Abstract/AbstractText"):
        body = text_of(node)
        label = (node.get("Label") or "").strip()
        if body:
            parts.append(f"{label.capitalize()}: {body}" if label else body)
    return " ".join(parts)


def _year(article: Element) -> int | None:
    issue = article.find("MedlineCitation/Article/Journal/JournalIssue/PubDate")
    if issue is not None:
        year = text_of(issue.find("Year")) or text_of(issue.find("MedlineDate"))
        match = _DIGITS.search(year)
        if match:
            return int(match.group(0))
    return None


def to_work(article: Element) -> Work:
    cit = "MedlineCitation/Article/"
    ids = _article_ids(article)
    pmid = text_of(article.find("MedlineCitation/PMID"))
    pub_types = [text_of(t) for t in article.findall(cit + "PublicationTypeList/PublicationType")]
    pmcid = ids.get("pmc", "")
    authors = tuple(
        Author(family=text_of(a.find("LastName")), given=text_of(a.find("ForeName")) or text_of(a.find("Initials")))
        for a in article.findall(cit + "AuthorList/Author") if text_of(a.find("LastName"))
    )
    pagination = text_of(article.find(cit + "Pagination/MedlinePgn"))
    languages = article.findall(cit + "Language")
    return Work(
        ref=pmid,
        title=text_of(article.find(cit + "ArticleTitle")).rstrip(".") or "Título não informado",
        authors=authors,
        journal=text_of(article.find(cit + "Journal/Title")),
        year=_year(article),
        volume=text_of(article.find(cit + "Journal/JournalIssue/Volume")),
        issue=text_of(article.find(cit + "Journal/JournalIssue/Issue")),
        pages=pagination,
        doi=ids.get("doi", ""), pmid=pmid, pmcid=pmcid,
        study_types=tuple(label for label in study_type_labels(pub_types) if label in _KNOWN_LABELS),
        open_access=bool(pmcid),
        oa_url=f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/" if pmcid else "",
        language=iso2(text_of(languages[0])) if languages else "",
        abstract=_abstract(article),
        keywords=tuple(dict.fromkeys(
            text_of(k) for k in article.findall("MedlineCitation/KeywordList/Keyword") if text_of(k)))[:MAX_KEYWORDS],
        source="PubMed",
        retracted="retracted publication" in {t.lower() for t in pub_types},
    )


class PubMedCatalog:
    id = "pubmed"
    name = "PubMed (MEDLINE)"
    combined = False

    def __init__(self, api_key: str = "") -> None:
        self._api_key = api_key

    def study_types(self) -> tuple[str, ...]:
        return tuple(STUDY_FILTERS)

    def _get(self, endpoint: str, params: dict[str, str]) -> requests.Response:
        if self._api_key:
            params = {**params, "api_key": self._api_key}
        try:
            response = requests.get(BASE_URL + endpoint, params=params, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as error:
            logger.warning("PubMed indisponivel: {}", error)
            raise CatalogError("A busca no PubMed está indisponível agora. Tente novamente em instantes.") from error
        return response

    def _esearch(self, term: str, **extra: str) -> dict[str, Any]:
        try:
            data = self._get("esearch.fcgi", {"db": "pubmed", "term": term, "retmode": "json", **extra}).json()
        except ValueError as error:
            raise CatalogError("O PubMed devolveu uma resposta ilegível.") from error
        return data.get("esearchresult") or {}

    def _efetch(self, ids: list[str]) -> tuple[Work, ...]:
        if not ids:
            return ()
        root = parse_xml(self._get("efetch.fcgi", {"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}).content)
        by_id = {w.pmid: w for w in (to_work(a) for a in root.findall("PubmedArticle"))}
        return tuple(by_id[i] for i in ids if i in by_id)

    def search(self, query: SearchQuery) -> SearchResult:
        query = query.normalized()
        term = build_term(query)
        if not term:
            return SearchResult(works=(), total=0, page=query.page, per_page=query.per_page, source=self.id)
        sort = "pub_date" if query.sort == "recent" else "relevance"
        found = self._esearch(
            term, retstart=str((query.page - 1) * query.per_page), retmax=str(query.per_page), sort=sort)
        ids = [str(i) for i in found.get("idlist") or []]
        count = str(found.get("count") or "0")
        notes = ("O PubMed não ordena por citações; os resultados seguem a relevância.",) if query.sort == "cited" else ()
        return SearchResult(
            works=self._efetch(ids), total=int(count) if count.isdigit() else 0,
            page=query.page, per_page=query.per_page, source=self.id, notes=notes,
        )

    def get(self, ref: str) -> Work | None:
        ref = ref.strip()
        if ref.isdigit():
            ids = [ref]
        elif _PMC.match(ref.upper()):
            ids = [str(i) for i in self._esearch(f"{ref.upper()}[pmcid]").get("idlist") or []]
        elif _DOI.match(ref):
            ids = [str(i) for i in self._esearch(f"{_UNSAFE.sub('', ref)}[doi]").get("idlist") or []]
        else:
            return None
        works = self._efetch(ids[:1])
        return works[0] if works else None
