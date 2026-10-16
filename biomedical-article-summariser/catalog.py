"""Modelo de dominio da descoberta de artigos: obras, consultas e a interface de catalogos.

Um `Catalog` e uma fonte de busca (Europe PMC, OpenAlex...). A regra de projeto e "uma fonte
principal por busca": misturar varias APIs gera ordenacao e paginacao confusas, entao cada
busca consulta um unico catalogo e a interface deixa o usuario escolher qual.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from citations import Author

SORTS = ("relevance", "recent", "cited")
MAX_PER_PAGE = 20
MAX_QUERY_CHARS = 200
MAX_PAGE = 500


@dataclass(frozen=True)
class Work:
    """Um artigo como o catalogo o descreve. `ref` e o identificador que o resolvedor entende."""

    ref: str  # PMID, PMCID, DOI ou ID OpenAlex ("W...")
    title: str
    authors: tuple[Author, ...] = ()
    journal: str = ""
    year: int | None = None
    volume: str = ""
    issue: str = ""
    pages: str = ""
    doi: str = ""
    pmid: str = ""
    pmcid: str = ""
    study_types: tuple[str, ...] = ()  # rotulos do registro oficial, ja em portugues
    open_access: bool = False
    oa_url: str = ""
    cited_by: int = 0
    language: str = ""  # ISO 639-1 quando conhecido (pt, en, es...)
    abstract: str = ""
    keywords: tuple[str, ...] = ()
    source: str = ""

    @property
    def author_line(self) -> str:
        names = [f"{a.given} {a.family}".strip() for a in self.authors[:6]]
        return ", ".join(names) + (" et al." if len(self.authors) > 6 else "")


@dataclass(frozen=True)
class SearchQuery:
    q: str = ""
    year_from: int | None = None
    year_to: int | None = None
    study_types: tuple[str, ...] = ()
    open_access: bool = False
    language: str = ""  # "" = todos
    sort: str = "relevance"
    page: int = 1
    per_page: int = 10

    def normalized(self) -> SearchQuery:
        """Aplica limites e remove valores invalidos (a consulta vem da internet)."""
        # caracteres de controle viram espaco (apagar juntaria as palavras ao redor)
        q = " ".join("".join(ch if ch.isprintable() else " " for ch in self.q).split())[:MAX_QUERY_CHARS]
        year_from, year_to = self.year_from, self.year_to
        if year_from and year_to and year_from > year_to:
            year_from, year_to = year_to, year_from
        return SearchQuery(
            q=q,
            year_from=year_from if year_from and 1800 <= year_from <= 2100 else None,
            year_to=year_to if year_to and 1800 <= year_to <= 2100 else None,
            study_types=tuple(dict.fromkeys(t for t in self.study_types if t))[:10],
            open_access=bool(self.open_access),
            language=self.language[:2].lower() if self.language else "",
            sort=self.sort if self.sort in SORTS else "relevance",
            page=min(max(1, self.page), MAX_PAGE),
            per_page=min(max(1, self.per_page), MAX_PER_PAGE),
        )


@dataclass(frozen=True)
class SearchResult:
    works: tuple[Work, ...] = field(default_factory=tuple)
    total: int = 0
    page: int = 1
    per_page: int = 10
    source: str = ""

    @property
    def pages(self) -> int:
        return max(1, -(-self.total // self.per_page)) if self.total else 1


class CatalogError(RuntimeError):
    """A fonte de busca falhou (rede, formato ou limite). A mensagem e segura para o usuario."""


class Catalog(Protocol):
    id: str
    name: str

    def study_types(self) -> tuple[str, ...]:
        """Rotulos de filtro de tipo de estudo oferecidos por esta fonte (em portugues)."""

    def search(self, query: SearchQuery) -> SearchResult: ...

    def get(self, ref: str) -> Work | None: ...


ISO3_TO_ISO2 = {
    "eng": "en", "por": "pt", "spa": "es", "fre": "fr", "fra": "fr", "ger": "de", "deu": "de", "ita": "it",
    "chi": "zh", "zho": "zh", "jpn": "ja", "rus": "ru", "dut": "nl", "nld": "nl", "pol": "pl", "tur": "tr",
}
ISO2_TO_ISO3 = {"en": "eng", "pt": "por", "es": "spa", "fr": "fre", "de": "ger", "it": "ita"}


def iso2(code: str) -> str:
    code = (code or "").strip().lower()
    if len(code) == 2:
        return code
    return ISO3_TO_ISO2.get(code, code[:2])
