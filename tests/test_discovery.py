import pytest

from catalog import CatalogError, SearchQuery, SearchResult, Work
from citations import Author
from discovery import DiscoveryService, citation_metadata
from domain import ArticleNotFoundError, DiggerError, RateLimitedError, SourceUnavailableError
from ratelimit import SlidingWindowLimiter

ABSTRACT = (
    "Background: Metformin is widely used. Methods: We pooled 14 trials (n=18,450). "
    "Results: Lower risk (RR 0.89; 95% CI 0.81-0.98; p=0.02). Conclusions: A modest reduction."
)


def make_work(ref="1", **overrides):
    base = {
        "ref": ref, "title": f"Artigo {ref}", "authors": (Author("Weber", "Anika"), Author("Suzuki", "Hiro")),
        "journal": "Example Journal", "year": 2020, "volume": "27", "issue": "5", "pages": "890-903", "doi": f"10.0000/{ref}",
        "pmid": ref, "abstract": ABSTRACT, "keywords": ("metformin", "diabetes", "heart"), "source": "Europe PMC", "cited_by": 10,
    }
    base.update(overrides)
    return Work(**base)


class FakeCatalog:
    def __init__(self, id="europepmc", name="Europe PMC (ciências da vida)", works=None, fail=False):
        self.id, self.name, self.fail = id, name, fail
        self.works = {w.ref: w for w in (works or [])}
        self.search_calls, self.get_calls = [], []

    def study_types(self):
        return ("Revisão",)

    def search(self, query):
        self.search_calls.append(query)
        if self.fail:
            raise CatalogError("A busca está indisponível agora.")
        found = tuple(self.works.values())
        return SearchResult(works=found, total=len(found), page=query.page, per_page=query.per_page, source=self.id)

    def get(self, ref):
        self.get_calls.append(ref)
        if self.fail:
            raise CatalogError("indisponível")
        return self.works.get(ref)


def service(*catalogs, limit=100, fallback=None):
    return DiscoveryService(catalogs or [FakeCatalog(works=[make_work("1"), make_work("2")])],
                            SlidingWindowLimiter(limit, 60), fallback=fallback)


# ------------------------------------------------------------------ busca
def test_search_returns_results_and_caches_identical_queries_without_spending_the_limit():
    catalog = FakeCatalog(works=[make_work("1")])
    svc = service(catalog, limit=1)
    first = svc.search(SearchQuery(q="metformin"))
    second = svc.search(SearchQuery(q="metformin"))  # cache: nao gasta o limite de 1
    assert first is second and len(catalog.search_calls) == 1


def test_query_is_normalized_before_reaching_the_catalog_and_before_caching():
    catalog = FakeCatalog(works=[make_work("1")])
    svc = service(catalog)
    svc.search(SearchQuery(q="  diabetes \x00 tipo  ", per_page=999))
    svc.search(SearchQuery(q="diabetes tipo", per_page=20))  # mesma consulta normalizada
    assert len(catalog.search_calls) == 1 and catalog.search_calls[0].per_page == 20


def test_rate_limit_applies_per_identity_and_only_to_uncached_searches():
    svc = service(limit=2)
    svc.search(SearchQuery(q="a"), client_id="x")
    svc.search(SearchQuery(q="b"), client_id="x")
    with pytest.raises(RateLimitedError):
        svc.search(SearchQuery(q="c"), client_id="x")
    svc.search(SearchQuery(q="c"), client_id="y")


def test_catalog_failure_becomes_a_source_unavailable_error_and_is_not_cached():
    broken = FakeCatalog(fail=True)
    svc = service(broken)
    for _ in range(2):
        with pytest.raises(SourceUnavailableError, match="indisponível"):
            svc.search(SearchQuery(q="x"))
    assert len(broken.search_calls) == 2


def test_sources_listing_and_unknown_source():
    svc = service(FakeCatalog(), FakeCatalog(id="openalex", name="OpenAlex (todas as áreas)"))
    listing = svc.sources()
    assert [s["id"] for s in listing] == ["europepmc", "openalex"] and listing[0]["default"] is True
    assert svc.default_source == "europepmc"
    with pytest.raises(DiggerError, match="desconhecida"):
        svc.search(SearchQuery(q="x"), source="google")


def test_search_routes_to_the_chosen_source():
    epmc, alex = FakeCatalog(works=[make_work("1")]), FakeCatalog(id="openalex", name="OpenAlex (x)", works=[make_work("W1")])
    svc = service(epmc, alex)
    svc.search(SearchQuery(q="x"), source="openalex")
    assert alex.search_calls and not epmc.search_calls


def test_service_requires_at_least_one_catalog():
    with pytest.raises(ValueError):
        DiscoveryService([], SlidingWindowLimiter(1, 60))


# ------------------------------------------------------------------ obra
def test_work_detail_has_sections_findings_citations_and_similar():
    catalog = FakeCatalog(works=[make_work("1"), make_work("2"), make_work("3")])
    detail = service(catalog).detail("1")
    assert detail.work.ref == "1"
    assert [s.heading for s in detail.sections] == ["Contexto", "Métodos", "Resultados", "Conclusões"]
    assert any("RR 0.89" in f.sentence and "medida de efeito" in f.tags for f in detail.findings)
    assert set(detail.citations) == {"ABNT", "APA", "Vancouver"}
    assert detail.citations["Vancouver"] == "Weber A, Suzuki H. Artigo 1. Example Journal. 2020;27(5):890-903. doi:10.0000/1"
    assert detail.citations["ABNT"].startswith("WEBER, A.; SUZUKI, H. Artigo 1.")
    assert [w.ref for w in detail.similar] == ["2", "3"]  # sem a propria obra


def test_work_uses_the_search_cache_so_opening_a_result_costs_no_extra_call():
    catalog = FakeCatalog(works=[make_work("1")])
    svc = service(catalog)
    svc.search(SearchQuery(q="x"))
    assert svc.work("1").title == "Artigo 1" and catalog.get_calls == []


def test_work_is_found_in_the_first_catalog_that_has_it():
    epmc = FakeCatalog(works=[])
    alex = FakeCatalog(id="openalex", name="OpenAlex (x)", works=[make_work("W9", source="OpenAlex")])
    assert service(epmc, alex).work("W9").source == "OpenAlex"
    assert epmc.get_calls == ["W9"] and alex.get_calls == ["W9"]


def test_work_not_found_anywhere_raises_not_found_and_uses_fallback_when_available():
    with pytest.raises(ArticleNotFoundError):
        service(FakeCatalog(works=[]), fallback=None).work("999")
    minimal = Work(ref="10.1/x", title="Só resumo", abstract="Um resumo.", source="Crossref")
    assert service(FakeCatalog(works=[]), fallback=lambda ref: minimal).work("10.1/x") is minimal


def test_all_catalogs_down_without_fallback_is_source_unavailable():
    with pytest.raises(SourceUnavailableError):
        service(FakeCatalog(fail=True), fallback=None).work("1")


def test_work_input_is_validated_and_rate_limited():
    svc = service(limit=1)
    with pytest.raises(DiggerError, match="identificador"):
        svc.work("   ")
    svc.work("1", client_id="a")
    svc.work("1", client_id="a")  # cache
    with pytest.raises(RateLimitedError):
        svc.work("zzz", client_id="a")


def test_similar_is_best_effort_and_needs_keywords():
    assert service().similar(make_work("1", keywords=())) == ()
    catalog = FakeCatalog(works=[make_work("1")])
    svc = service(catalog)
    assert svc.similar(make_work("1")) == ()  # so ha a propria obra
    broken = service(FakeCatalog(fail=True))
    assert broken.similar(make_work("1")) == ()  # falha da fonte nao derruba a pagina


def test_similar_uses_the_same_catalog_the_work_came_from():
    epmc = FakeCatalog(works=[make_work("1")])
    alex = FakeCatalog(id="openalex", name="OpenAlex (todas as áreas)", works=[make_work("W1", source="OpenAlex"), make_work("W2", source="OpenAlex")])
    svc = service(epmc, alex)
    result = svc.similar(make_work("W1", source="OpenAlex"))
    assert alex.search_calls and not epmc.search_calls and [w.ref for w in result] == ["W2"]


def test_citation_metadata_mirrors_the_work():
    meta = citation_metadata(make_work("1"))
    assert (meta.title, meta.year, meta.volume, meta.issue, meta.pages, meta.doi) == ("Artigo 1", "2020", "27", "5", "890-903", "10.0000/1")


# ------------------------------------------------------------------ serializacao
def test_work_roundtrips_through_dict():
    work = make_work("1", study_types=("Meta-análise",), open_access=True, oa_url="https://x/y", language="en")
    assert Work.from_dict(work.to_dict()) == work


def test_work_from_dict_tolerates_garbage():
    work = Work.from_dict({"ref": 5, "title": None, "authors": [{"family": "A"}, "lixo", {"given": "x"}], "year": "2020",
                           "cited_by": "muitos", "keywords": "nao-lista", "open_access": "sim"})
    assert work.ref == "" and work.title == "Título não informado" and work.authors == (Author("A", ""),)
    assert work.year is None and work.cited_by == 0 and work.keywords == () and work.open_access is False
    assert Work.from_dict({}).title == "Título não informado"
