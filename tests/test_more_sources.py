"""Catalogos arXiv, DOAJ, OpenAIRE e PubMed, enriquecimento e busca combinada (HTTP simulado)."""

from unittest.mock import MagicMock, patch

import pytest
import requests

import arxiv_catalog
import doaj_catalog
import enrichment
import openaire_catalog
import pubmed_catalog
from arxiv_catalog import ArxivCatalog
from catalog import CatalogError, SearchQuery, SearchResult, Work
from discovery import DiscoveryService
from doaj_catalog import DoajCatalog
from enrichment import Enricher
from openaire_catalog import OpenAireCatalog
from pubmed_catalog import PubMedCatalog
from ratelimit import SlidingWindowLimiter
from xmlutil import parse_xml

ARXIV = b"""<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns:arxiv="http://arxiv.org/schemas/atom" xmlns="http://www.w3.org/2005/Atom">
  <opensearch:totalResults>330</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/1908.09038v2</id>
    <published>2019-08-23T20:59:42Z</published>
    <title>Pediatric  Sepsis
      Subphenotypes</title>
    <summary>Background: ML models are promising.</summary>
    <author><name>Ana Maria da Silva</name></author><author><name>Hiro Suzuki</name></author>
    <link href="https://arxiv.org/pdf/1908.09038v2" rel="related" type="application/pdf" title="pdf"/>
    <arxiv:doi>10.1000/xyz</arxiv:doi>
    <arxiv:journal_ref>Proc. Example 2020</arxiv:journal_ref>
  </entry>
</feed>"""

DOAJ = {
    "total": 1015,
    "results": [{"id": "abc123", "bibjson": {
        "title": "Monocyte distribution width", "abstract": "Resumo.", "year": "2025",
        "identifier": [{"id": "10.1080/22221751.2025.2479634", "type": "doi"}, {"id": "2222-1751", "type": "eissn"}],
        "journal": {"title": "Emerging Microbes", "volume": "14", "number": "1", "language": ["EN"]},
        "author": [{"name": "Jinfeng Sun"}], "keywords": ["sepsis", "sepsis"], "start_page": "1", "end_page": "9",
        "link": [{"type": "fulltext", "url": "https://example.org/full"}],
    }}],
}

OPENAIRE = {
    "header": {"numFound": 2648},
    "results": [{
        "mainTitle": "Derivation of <i>sepsis</i> phenotypes", "publicationDate": "2019-05-28",
        "descriptions": ["Sepsis is <b>heterogeneous</b>."], "bestAccessRight": {"label": "OPEN"},
        "authors": [{"surname": "Seymour", "name": "Christopher W."}, {"surname": "", "name": "x"}],
        "pids": [{"scheme": "doi", "value": "10.1001/jama.2019.5791"}, {"scheme": "pmid", "value": "31104070"}],
        "container": {"name": "JAMA", "vol": "321", "sp": "2003", "ep": "2017"},
        "instances": [{"urls": ["javascript:alert(1)", "https://doi.org/10.1001/jama.2019.5791"]}],
        "indicators": {"citationImpact": {"citationCount": 1307.0}}, "language": {"code": "eng"},
    }],
}

PUBMED_XML = b"""<?xml version="1.0" ?>
<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2025//EN" "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_250101.dtd">
<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID Version="1">31965266</PMID><Article>
<Journal><JournalIssue><Volume>46</Volume><Issue>3</Issue><PubDate><Year>2020</Year></PubDate></JournalIssue><Title>Intensive care medicine</Title></Journal>
<ArticleTitle>Machine learning for the prediction of <i>sepsis</i>: a review.</ArticleTitle>
<Pagination><MedlinePgn>383-400</MedlinePgn></Pagination>
<Abstract><AbstractText Label="PURPOSE">Early recognition is hard.</AbstractText><AbstractText Label="METHODS">We searched PubMed.</AbstractText></Abstract>
<AuthorList><Author><LastName>Fleuren</LastName><ForeName>Lucas M</ForeName></Author><Author><CollectiveName>Grupo</CollectiveName></Author></AuthorList>
<Language>eng</Language>
<PublicationTypeList><PublicationType>Meta-Analysis</PublicationType><PublicationType>Journal Article</PublicationType></PublicationTypeList>
</Article><KeywordList><Keyword>sepsis</Keyword></KeywordList></MedlineCitation>
<PubmedData><ArticleIdList><ArticleId IdType="pubmed">31965266</ArticleId><ArticleId IdType="doi">10.1007/s00134-019-05872-y</ArticleId><ArticleId IdType="pmc">PMC7042</ArticleId></ArticleIdList></PubmedData>
</PubmedArticle></PubmedArticleSet>"""


def response(*, content=b"", json=None, status=200):
    resp = MagicMock()
    resp.content = content
    resp.status_code = status
    resp.json.return_value = json
    resp.raise_for_status.side_effect = None if status < 400 else requests.HTTPError("boom")
    return resp


@pytest.fixture(autouse=True)
def no_throttle(monkeypatch):
    monkeypatch.setattr(arxiv_catalog, "_throttle", lambda: None)


# ------------------------------------------------------------------ xml seguro
def test_xml_with_entity_declarations_is_refused_but_external_dtd_reference_is_ignored():
    with pytest.raises(CatalogError):
        parse_xml(b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x "boom">]><a>&x;</a>')
    assert parse_xml(PUBMED_XML).tag == "PubmedArticleSet"
    with pytest.raises(CatalogError):
        parse_xml(b"<a><b></a>")


# ------------------------------------------------------------------ arXiv
def test_arxiv_maps_entries_and_builds_a_safe_query():
    with patch.object(arxiv_catalog.requests, "get", return_value=response(content=ARXIV)) as get:
        result = ArxivCatalog().search(SearchQuery(q='sepsis "x" OR; drop', year_from=2020, sort="cited", open_access=True))
    params = get.call_args.kwargs["params"]
    assert params["search_query"].startswith("all:sepsis AND all:x AND all:OR AND all:drop")
    assert "submittedDate:[20200101" in params["search_query"] and params["sortBy"] == "relevance"
    work = result.works[0]
    assert result.total == 330 and len(result.notes) == 2
    assert work.ref == "1908.09038" and work.title == "Pediatric Sepsis Subphenotypes" and work.year == 2019
    assert work.study_types == ("Preprint",) and work.open_access and work.doi == "10.1000/xyz"
    assert work.journal == "Proc. Example 2020" and [a.family for a in work.authors] == ["da Silva", "Suzuki"]
    assert work.oa_url == "https://arxiv.org/pdf/1908.09038v2" and work.source == "arXiv"


def test_arxiv_recent_sort_empty_query_get_and_errors():
    cat = ArxivCatalog()
    with patch.object(arxiv_catalog.requests, "get", return_value=response(content=ARXIV)) as get:
        cat.search(SearchQuery(q="sepsis", sort="recent"))
        assert get.call_args.kwargs["params"]["sortBy"] == "submittedDate"
        assert cat.search(SearchQuery(q="   ")).total == 0 and get.call_count == 1
        assert cat.get("not an id") is None and cat.get("1908.09038v2").ref == "1908.09038"
        assert get.call_args.kwargs["params"]["id_list"] == "1908.09038"
    with patch.object(arxiv_catalog.requests, "get", side_effect=requests.ConnectionError("x")), pytest.raises(CatalogError, match="arXiv"):
        cat.search(SearchQuery(q="sepsis"))


# ------------------------------------------------------------------ DOAJ
def test_doaj_maps_records_and_sanitises_the_query():
    with patch.object(doaj_catalog.requests, "get", return_value=response(json=DOAJ)) as get:
        result = DoajCatalog().search(SearchQuery(q='sepsis AND "x" bibjson.year:[1 TO 2]', year_from=2020, language="pt", sort="recent"))
    url = get.call_args.args[0]
    assert "%22" not in url and "%5B1" not in url and "sepsis" in url
    work = result.works[0]
    assert result.total == 1015 and result.notes
    assert work.ref == work.doi == "10.1080/22221751.2025.2479634" and work.open_access and work.language == "en"
    assert work.keywords == ("sepsis",) and work.pages == "1-9" and work.oa_url == "https://example.org/full"


def test_doaj_get_by_doi_and_internal_id():
    cat = DoajCatalog()
    with patch.object(doaj_catalog.requests, "get", return_value=response(json=DOAJ)) as get:
        assert cat.get("10.1080/22221751.2025.2479634").title == "Monocyte distribution width"
        assert "doi%3A10.1080" in get.call_args.args[0]
        assert cat.get("doaj:abc123") and "id%3Aabc123" in get.call_args.args[0]
        assert cat.get("doaj:ab c;") is None and cat.get("W123") is None
    with patch.object(doaj_catalog.requests, "get", return_value=response(json={"total": 0, "results": []})):
        assert cat.get("10.1/none") is None


# ------------------------------------------------------------------ OpenAIRE
def test_openaire_maps_records_and_applies_supported_filters():
    with patch.object(openaire_catalog.requests, "get", return_value=response(json=OPENAIRE)) as get:
        result = OpenAireCatalog().search(SearchQuery(q='sepsis "x"', year_from=2019, year_to=2020, sort="cited", open_access=True))
    params = get.call_args.kwargs["params"]
    assert params["sortBy"] == "citationCount DESC" and params["fromPublicationDate"] == "2019-01-01"
    assert params["toPublicationDate"] == "2020-12-31" and '"' not in params["search"]
    work = result.works[0]
    assert result.total == 2648 and result.notes and work.ref == "31104070" and work.cited_by == 1307
    assert work.title == "Derivation of sepsis phenotypes" and work.abstract == "Sepsis is heterogeneous."
    assert work.open_access and work.oa_url == "https://doi.org/10.1001/jama.2019.5791"  # esquema perigoso descartado
    assert work.pages == "2003-2017" and [a.family for a in work.authors] == ["Seymour"]


def test_openaire_get_validates_the_reference_and_handles_failures():
    cat = OpenAireCatalog()
    with patch.object(openaire_catalog.requests, "get", return_value=response(json=OPENAIRE)) as get:
        assert cat.get("10.1001/jama.2019.5791") and cat.get("31104070") and cat.get("PMC6537818")
        assert cat.get("x; drop") is None and get.call_count == 3
        assert cat.search(SearchQuery(q="")).total == 0
    with patch.object(openaire_catalog.requests, "get", return_value=response(status=500)), pytest.raises(CatalogError, match="OpenAIRE"):
        cat.search(SearchQuery(q="sepsis"))


# ------------------------------------------------------------------ PubMed
def test_pubmed_search_builds_filters_and_maps_structured_abstracts():
    esearch = response(json={"esearchresult": {"count": "2266", "idlist": ["31965266"]}})
    efetch = response(content=PUBMED_XML)
    with patch.object(pubmed_catalog.requests, "get", side_effect=[esearch, efetch]) as get:
        result = PubMedCatalog("KEY").search(SearchQuery(
            q='sepsis [ai] "x"', year_from=2020, year_to=2024, open_access=True, language="pt",
            study_types=("Meta-análise",), sort="recent", page=2, per_page=10))
    params = get.call_args_list[0].kwargs["params"]
    term = params["term"]
    assert "[ai]" not in term and '("2020"[dp] : "2024"[dp])' in term and "free full text[sb]" in term
    assert "por[la]" in term and '"Meta-Analysis"[pt]' in term
    assert params["sort"] == "pub_date" and params["retstart"] == "10" and params["api_key"] == "KEY"
    work = result.works[0]
    assert result.total == 2266 and work.ref == work.pmid == "31965266" and work.pmcid == "PMC7042"
    assert work.title == "Machine learning for the prediction of sepsis: a review"
    assert work.abstract == "Purpose: Early recognition is hard. Methods: We searched PubMed."
    assert work.study_types == ("Meta-análise",) and work.open_access and work.year == 2020 and work.language == "en"
    assert [a.family for a in work.authors] == ["Fleuren"] and work.keywords == ("sepsis",)
    assert work.doi == "10.1007/s00134-019-05872-y" and work.source == "PubMed"


def test_pubmed_get_by_pmid_doi_and_pmc_and_empty_cases():
    cat = PubMedCatalog()
    with patch.object(pubmed_catalog.requests, "get", return_value=response(content=PUBMED_XML)) as get:
        assert cat.get("31965266").pmid == "31965266" and get.call_count == 1
        assert cat.get("not valid") is None
        assert cat.search(SearchQuery(q="")).total == 0
    with patch.object(pubmed_catalog.requests, "get",
                      side_effect=[response(json={"esearchresult": {"idlist": ["31965266"]}}), response(content=PUBMED_XML)]) as get:
        assert cat.get("10.1007/s00134-019-05872-y").pmid == "31965266"
        assert "[doi]" in get.call_args_list[0].kwargs["params"]["term"]
    with patch.object(pubmed_catalog.requests, "get", return_value=response(json={"esearchresult": {"idlist": []}})):
        assert cat.get("10.1/none") is None
        assert cat.search(SearchQuery(q="nada")).works == ()
    with patch.object(pubmed_catalog.requests, "get", side_effect=requests.Timeout("x")), pytest.raises(CatalogError, match="PubMed"):
        cat.search(SearchQuery(q="sepsis"))


def test_pubmed_retracted_publications_are_flagged():
    xml = PUBMED_XML.replace(b"<PublicationType>Journal Article</PublicationType>", b"<PublicationType>Retracted Publication</PublicationType>")
    work = pubmed_catalog.to_work(parse_xml(xml).find("PubmedArticle"))
    assert work.retracted


# ------------------------------------------------------------------ enriquecimento
def work_with(abstract="", doi="10.1038/nature12373"):
    return Work(ref="9", title="T", abstract=abstract, doi=doi)


def fake_json(url, params=None):
    if "clinicaltrials.gov" in url:
        if "NCT00000000" in url:
            return None
        return {"protocolSection": {"identificationModule": {"nctId": "NCT04280705", "briefTitle": "ACTT"},
                                    "statusModule": {"overallStatus": "COMPLETED", "startDateStruct": {"date": "2020-02-21"}}},
                "hasResults": True}
    if "opencitations" in url:
        return [{"count": "1806"}]
    return {"data": [
        {"attributes": {"doi": "10.5281/zenodo.1", "titles": [{"title": "Dados do estudo"}], "publisher": "Zenodo",
                        "types": {"resourceTypeGeneral": "Dataset"}}},
        {"attributes": {"doi": "10.1/artigo", "titles": [{"title": "Outro artigo"}], "types": {"resourceTypeGeneral": "JournalArticle"}}},
        {"attributes": {"doi": "ruim", "titles": [{"title": "DOI invalido"}], "types": {"resourceTypeGeneral": "Dataset"}}},
    ]}


def test_enricher_combines_trials_citations_and_related_data_and_caches():
    work = work_with("Registered as NCT04280705 and NCT00000000; again NCT04280705.")
    with patch.object(enrichment, "_get_json", side_effect=fake_json) as get:
        enricher = Enricher()
        result = enricher.enrich(work)
        assert result.mentioned_trials == ("NCT04280705", "NCT00000000")
        assert [t.nct for t in result.trials] == ["NCT04280705"] and result.trials[0].status == "Concluído"
        assert result.trials[0].has_results and result.trials[0].url == "https://clinicaltrials.gov/study/NCT04280705"
        assert result.citations == 1806
        assert [d.doi for d in result.related_data] == ["10.5281/zenodo.1"] and result.related_data[0].url.startswith("https://doi.org/")
        calls = get.call_count
        assert enricher.enrich(work) is result and get.call_count == calls  # segunda leitura vem do cache


def test_enricher_does_not_cache_failures_so_the_next_visit_retries():
    work = work_with("NCT04280705")
    enricher = Enricher()
    with patch.object(enrichment, "_get_json", side_effect=requests.Timeout("lento")):
        assert enricher.enrich(work).citations is None
    assert enricher.cached(work) is None
    with patch.object(enrichment, "_get_json", side_effect=fake_json):
        assert enricher.enrich(work).citations == 1806
    assert enricher.cached(work) is not None


def test_enricher_survives_failures_and_skips_invalid_doi():
    with patch.object(enrichment, "_get_json", side_effect=requests.ConnectionError("x")):
        result = Enricher().enrich(work_with("NCT04280705"))
    assert result.trials == () and result.citations is None and result.related_data == ()
    with patch.object(enrichment, "_get_json") as get:
        result = Enricher().enrich(work_with("sem registro", doi="10.1/a;rm -rf"))
        get.assert_not_called()
    assert result == enrichment.Enrichment()


# ------------------------------------------------------------------ busca combinada
class Stub:
    def __init__(self, id, name, combined=True, works=()):
        self.id, self.name, self.combined, self._works = id, name, combined, works

    def study_types(self):
        return ()

    def search(self, query):
        return SearchResult(works=tuple(self._works), total=len(self._works), page=1, per_page=10, source=self.id)

    def get(self, ref):
        return next((w for w in self._works if w.ref == ref), None)


def test_combined_search_only_uses_main_catalogs_and_names_them():
    main = Stub("europepmc", "Europe PMC (ciências da vida)", works=[Work(ref="1", title="Principal", doi="10.1/a")])
    second = Stub("openalex", "OpenAlex (todas as áreas)", works=[Work(ref="W2", title="Segundo", doi="10.1/b")])
    extra = Stub("arxiv", "arXiv (computação)", combined=False, works=[Work(ref="x", title="Extra")])
    svc = DiscoveryService([main, second, extra], SlidingWindowLimiter(100, 60), fallback=None)
    listing = svc.sources()
    assert [s["id"] for s in listing] == ["all", "europepmc", "openalex", "arxiv"] and listing[0]["name"] == "Europe PMC + OpenAlex"
    assert {w.ref for w in svc.search(SearchQuery(q="x"), source="all").works} == {"1", "W2"}
    assert [w.ref for w in svc.search(SearchQuery(q="x"), source="arxiv").works] == ["x"]


def test_no_combined_option_when_only_one_main_catalog():
    svc = DiscoveryService([Stub("europepmc", "Europe PMC (x)"), Stub("arxiv", "arXiv (x)", combined=False)],
                           SlidingWindowLimiter(100, 60), fallback=None)
    assert [s["id"] for s in svc.sources()] == ["europepmc", "arxiv"]


def test_discovery_enrich_uses_the_work_and_caches_without_spending_the_limit():
    cat = Stub("europepmc", "Europe PMC (x)", works=[Work(ref="9", title="T", abstract="NCT04280705", doi="10.1038/nature12373")])
    svc = DiscoveryService([cat], SlidingWindowLimiter(2, 60), fallback=None)
    with patch.object(enrichment, "_get_json", side_effect=fake_json):
        first = svc.enrich("9")
        assert first.citations == 1806
        for _ in range(5):
            assert svc.enrich("9") is first


# ------------------------------------------------------------------ todas as fontes de verdade
class Recorder(Stub):
    def __init__(self, id, name, works=(), delay=0.0, **kw):
        super().__init__(id, name, works=works, **kw)
        self.per_pages, self.delay = [], delay

    def search(self, query):
        import time
        self.per_pages.append(query.per_page)
        time.sleep(self.delay)
        return super().search(query)


def test_all_sources_name_and_slice_the_page_between_sources():
    cats = [Recorder(f"s{i}", f"Fonte {i} (x)", works=[Work(ref=f"{i}-{n}", title=f"T{i}{n}", doi=f"10.1/{i}-{n}") for n in range(3)])
            for i in range(5)]
    svc = DiscoveryService(cats, SlidingWindowLimiter(100, 60), fallback=None)
    assert svc.sources()[0]["name"] == "Todas as fontes"
    result = svc.search(SearchQuery(q="x", per_page=10), source="all")
    assert all(c.per_pages == [2] for c in cats)  # 10 / 5 fontes = 2 por fonte
    assert len(result.works) == 15 and result.total == 15


def test_slow_source_is_left_out_with_a_note_but_warms_the_cache(monkeypatch):
    import discovery
    monkeypatch.setattr(discovery, "ALL_DEADLINE", 0.2)
    fast = Recorder("a", "Rapida (x)", works=[Work(ref="1", title="Rapida", doi="10.1/a")])
    slow = Recorder("b", "Lenta (x)", works=[Work(ref="2", title="Lenta", doi="10.1/b")], delay=0.8)
    svc = DiscoveryService([fast, slow], SlidingWindowLimiter(100, 60), fallback=None)
    result = svc.search(SearchQuery(q="x"), source="all")
    assert [w.ref for w in result.works] == ["1"]
    assert any("Lenta demorou demais" in n for n in result.notes)
    import time
    time.sleep(1.0)  # a fonte lenta termina sozinha e deixa o resultado no cache da fonte
    assert [w.ref for w in svc.search(SearchQuery(q="x", per_page=5), source="b").works] == ["2"]
    assert slow.per_pages == [5]  # a segunda leitura veio do cache, sem nova chamada


def test_slowest_source_does_not_hold_the_page_once_enough_sources_answered(monkeypatch):
    import time

    import discovery
    monkeypatch.setattr(discovery, "ALL_GRACE", 0.2)
    monkeypatch.setattr(discovery, "READY_SOURCES", 2)
    fast = [Recorder(f"f{i}", f"Rapida {i} (x)", works=[Work(ref=f"f{i}", title=f"R{i}", doi=f"10.1/f{i}")]) for i in range(2)]
    slow = Recorder("s", "Lenta (x)", works=[Work(ref="s", title="Lenta", doi="10.1/s")], delay=3.0)
    svc = DiscoveryService([*fast, slow], SlidingWindowLimiter(100, 60), fallback=None)
    started = time.monotonic()
    result = svc.search(SearchQuery(q="x"), source="all")
    assert time.monotonic() - started < 1.5  # nao esperou os 3 s da fonte lenta
    assert {w.ref for w in result.works} == {"f0", "f1"}
    assert any("Lenta demorou demais" in n for n in result.notes)


def test_search_default_is_all_sources_when_there_is_more_than_one():
    one = DiscoveryService([Stub("europepmc", "Europe PMC (x)")], SlidingWindowLimiter(100, 60), fallback=None)
    assert one.search_default == "europepmc" and one.sources()[0]["default"] is True
    two = DiscoveryService([Stub("europepmc", "Europe PMC (x)", works=[Work(ref="1", title="A", doi="10.1/a")]),
                            Stub("arxiv", "arXiv (x)", works=[Work(ref="2", title="B", doi="10.1/b")])],
                           SlidingWindowLimiter(100, 60), fallback=None)
    listing = two.sources()
    assert two.search_default == "all" and [s["id"] for s in listing if s["default"]] == ["all"]
    assert {w.ref for w in two.search(SearchQuery(q="x"), source=two.search_default).works} == {"1", "2"}


# ------------------------------------------------------------------ artigos semelhantes
def test_similar_terms_use_keywords_or_the_longest_title_words():
    svc = DiscoveryService([Stub("europepmc", "Europe PMC (x)")], SlidingWindowLimiter(100, 60), fallback=None)
    with_keywords = Work(ref="1", title="Algo", keywords=("Humans", "sepsis", "Pneumonia, Viral", "Male", "extra"))
    assert svc.similar_terms(with_keywords) == ["sepsis", "Pneumonia Viral"]  # termos genericos fora, virgula some
    mixed = Work(ref="2", title="Early prediction of sepsis using machine learning in the intensive care unit", keywords=("so uma",))
    assert svc.similar_terms(mixed) == ["so uma", "prediction", "intensive"]
    no_keywords = Work(ref="4", title="Remdesivir for the Treatment of Covid-19 - Final Report")
    assert svc.similar_terms(no_keywords) == ["remdesivir", "covid"]
    assert svc.similar_terms(Work(ref="3", title="Um de em")) == []


def test_similar_searches_by_relevance_excludes_the_work_and_same_titles():
    own = Work(ref="1", title="Sepsis prediction with machine learning", doi="10.1/a", keywords=("sepsis", "machine learning"))
    cat = Recorder("europepmc", "Europe PMC (x)", works=[
        own, Work(ref="2", title="Outro artigo", doi="10.1/b"),
        Work(ref="3", title="Sepsis prediction with machine learning!", doi="10.1/c"),  # mesmo titulo (versao duplicada)
        Work(ref="4", title="Terceiro", doi="10.1/d"),
    ])
    queries = []
    original = cat.search
    cat.search = lambda q: (queries.append(q), original(q))[1]
    svc = DiscoveryService([cat], SlidingWindowLimiter(100, 60), fallback=None)
    assert [w.ref for w in svc.similar(own)] == ["2", "4"]
    assert queries[0].q == "sepsis machine learning prediction" and queries[0].sort == "relevance" and queries[0].per_page == 10
