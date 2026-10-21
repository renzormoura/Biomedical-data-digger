import pytest

from catalog import CatalogError, SearchQuery, SearchResult, Work
from citations import Author
from discovery import DiscoveryService, citation_metadata
from domain import ArticleNotFoundError, NexusError, RateLimitedError, SourceUnavailableError
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
    assert [s["id"] for s in listing] == ["all", "europepmc", "openalex"]
    assert listing[0]["name"] == "Todas as fontes" and listing[0]["default"] is True and listing[1]["default"] is False
    assert svc.default_source == "europepmc"
    with pytest.raises(NexusError, match="desconhecida"):
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
def svc_for(catalog):
    return service(catalog)


def test_work_detail_has_sections_findings_citations_and_similar():
    catalog = FakeCatalog(works=[make_work("1"), make_work("2"), make_work("3")])
    detail = service(catalog).detail("1")
    assert detail.work.ref == "1"
    assert [s.heading for s in detail.sections] == ["Contexto", "Métodos", "Resultados", "Conclusões"]
    assert any("RR 0.89" in f.sentence and "medida de efeito" in f.tags for f in detail.findings)
    assert set(detail.citations) == {"ABNT", "APA", "Vancouver", "IEEE", "Harvard", "MLA"}
    assert detail.citations["Vancouver"] == "Weber A, Suzuki H. Artigo 1. Example Journal. 2020;27(5):890-903. doi:10.0000/1"
    assert detail.citations["ABNT"].startswith("WEBER, A.; SUZUKI, H. Artigo 1.")
    assert detail.similar == ()  # os semelhantes carregam por rota propria
    assert [w.ref for w in svc_for(catalog).similar(detail.work)] == ["2", "3"]  # sem a propria obra


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
    with pytest.raises(NexusError, match="identificador"):
        svc.work("   ")
    svc.work("1", client_id="a")
    svc.work("1", client_id="a")  # cache
    with pytest.raises(RateLimitedError):
        svc.work("zzz", client_id="a")


def test_similar_is_best_effort_and_needs_usable_terms():
    assert service().similar(make_work("1", keywords=(), title="Um de")) == ()  # sem palavras-chave nem palavras de titulo
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


# ------------------------------------------------------------------ todas as fontes
def two_sources(epmc_works, alex_works, **kw):
    epmc = FakeCatalog(works=epmc_works, **kw.get("epmc", {}))
    alex = FakeCatalog(id="openalex", name="OpenAlex (todas as áreas)", works=alex_works, **kw.get("alex", {}))
    return epmc, alex, service(epmc, alex)


def test_single_source_has_no_all_option():
    assert [s["id"] for s in service(FakeCatalog()).sources()] == ["europepmc"]


def test_all_sources_merges_dedupes_by_doi_and_interleaves():
    shared_epmc = make_work("1", doi="10.1/shared", abstract="")
    shared_alex = make_work("W9", doi="10.1/SHARED", pmid="", source="OpenAlex")
    epmc, alex, svc = two_sources([shared_epmc, make_work("2")], [shared_alex, make_work("W3", doi="10.1/w3", pmid="")])
    result = svc.search(SearchQuery(q="x"), source="all")
    assert result.source == "all" and result.total == 4
    assert len(result.works) == 3  # o repetido (mesmo DOI, caixa diferente) aparece uma vez
    kept = next(w for w in result.works if w.doi.lower() == "10.1/shared")
    assert kept.abstract  # fica o registro mais completo
    assert len(epmc.search_calls) == 1 and len(alex.search_calls) == 1


def test_all_sources_sorts_by_citations_and_recency():
    epmc, alex, svc = two_sources([make_work("1", cited_by=5, year=2010)], [make_work("W2", doi="10.1/b", pmid="", cited_by=50, year=2024)])
    assert [w.ref for w in svc.search(SearchQuery(q="x", sort="cited"), source="all").works] == ["W2", "1"]
    assert [w.ref for w in svc.search(SearchQuery(q="x", sort="recent"), source="all").works] == ["W2", "1"]


def test_all_sources_survives_one_failure_with_a_note():
    epmc, alex, svc = two_sources([make_work("1")], [], alex={"fail": True})
    result = svc.search(SearchQuery(q="x"), source="all")
    assert [w.ref for w in result.works] == ["1"]
    assert any("OpenAlex não respondeu" in n for n in result.notes)


def test_all_sources_fails_only_when_every_source_fails():
    _, _, svc = two_sources([], [], epmc={"fail": True}, alex={"fail": True})
    with pytest.raises(SourceUnavailableError):
        svc.search(SearchQuery(q="x"), source="all")


def test_all_sources_skips_sources_without_the_chosen_study_type():
    epmc, alex, svc = two_sources([make_work("1")], [make_work("W2", doi="10.1/b", pmid="")])
    result = svc.search(SearchQuery(q="x", study_types=("Revisão",)), source="all")
    assert len(epmc.search_calls) == 1 and len(alex.search_calls) == 1  # ambas oferecem "Revisão"
    class NoTypes(FakeCatalog):
        def study_types(self):
            return ()
    svc2 = service(FakeCatalog(works=[make_work("1")]), NoTypes(id="openalex", name="OpenAlex (x)"))
    result = svc2.search(SearchQuery(q="x", study_types=("Revisão",)), source="all")
    assert any("OpenAlex não foi consultada" in n for n in result.notes)
    with pytest.raises(SourceUnavailableError, match="Nenhuma fonte oferece"):
        service(NoTypes(), NoTypes(id="b", name="B")).search(SearchQuery(q="x", study_types=("Revisão",)), source="all")


def test_all_sources_spends_the_limit_once_and_caches():
    epmc, alex, svc = two_sources([make_work("1")], [make_work("W2", doi="10.1/b", pmid="")])
    svc = DiscoveryService([epmc, alex], SlidingWindowLimiter(1, 60), fallback=None)
    first = svc.search(SearchQuery(q="x"), source="all")
    assert svc.search(SearchQuery(q="x"), source="all") is first


def test_work_lookup_accepts_the_all_source():
    _, _, svc = two_sources([make_work("1")], [])
    assert svc.work("1", source="all").ref == "1"
