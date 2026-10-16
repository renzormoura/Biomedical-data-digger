from unittest.mock import MagicMock, patch

import pytest
import requests

import europepmc_catalog as epmc
from catalog import CatalogError, SearchQuery, SearchResult, Work, iso2
from citations import Author
from europepmc_catalog import EuropePmcCatalog, build_query, clean_html_text, to_work

RECORD = {
    "id": "31263284", "source": "MED", "pmid": "31263284", "pmcid": "PMC6699990", "doi": "10.1038/s41591-019-0495-2",
    "title": "Supplementation with <i>Akkermansia muciniphila</i> in overweight and obese volunteers: a pilot study.",
    "pubYear": "2019", "pageInfo": "1096-1103", "citedByCount": 1769, "isOpenAccess": "Y", "language": "eng",
    "abstractText": "<h4>Background</h4><p>Obesity is linked to gut microbiota.</p><h4>Methods</h4><p>We enrolled 32 volunteers.</p>",
    "authorList": {"author": [
        {"fullName": "Depommier C", "lastName": "Depommier", "firstName": "Clara", "initials": "C"},
        {"fullName": "Everard A", "lastName": "Everard", "initials": "A"},
    ]},
    "journalInfo": {"issue": "7", "volume": "25", "journal": {"title": "Nature medicine"}},
    "fullTextUrlList": {"fullTextUrl": [
        {"availabilityCode": "S", "documentStyle": "doi", "url": "https://doi.org/10.1038/s41591-019-0495-2"},
        {"availabilityCode": "OA", "documentStyle": "pdf", "url": "https://europepmc.org/articles/PMC6699990?pdf=render"},
        {"availabilityCode": "OA", "documentStyle": "html", "url": "https://europepmc.org/articles/PMC6699990"},
    ]},
    "pubTypeList": {"pubType": ["Research Support, Non-U.S. Gov't", "research-article", "Randomized Controlled Trial", "Journal Article"]},
    "keywordList": {"keyword": ["microbiota", "obesity", "microbiota"]},
}


# ------------------------------------------------------------------ SearchQuery / catalogo
def test_query_normalization_clamps_and_cleans_untrusted_input():
    q = SearchQuery(q="  diabetes \x00 tipo\n2  ", year_from=2024, year_to=2019, study_types=("A", "", "A"),
                    language="PORTUGUES", sort="xyz", page=0, per_page=999).normalized()
    assert q.q == "diabetes tipo 2"
    assert (q.year_from, q.year_to) == (2019, 2024)
    assert q.study_types == ("A",) and q.language == "po" and q.sort == "relevance"
    assert q.page == 1 and q.per_page == 20
    assert SearchQuery(q="x" * 500).normalized().q == "x" * 200
    assert SearchQuery(year_from=1500, year_to=9999).normalized().year_from is None
    assert SearchQuery(page=10**9).normalized().page == 500


def test_search_result_pages_and_iso_helpers():
    assert SearchResult(total=0).pages == 1 and SearchResult(total=21, per_page=10).pages == 3
    assert (iso2("por"), iso2("ENG"), iso2("pt"), iso2("xyz"), iso2("")) == ("pt", "en", "pt", "xy", "")


def test_work_author_line_truncates():
    work = Work(ref="1", title="t", authors=tuple(Author(f"F{i}", "G") for i in range(8)))
    assert work.author_line.endswith("et al.") and work.author_line.count(",") == 5


# ------------------------------------------------------------------ consulta
def test_empty_query_with_filters_uses_has_abstract_and_combines_filters():
    query = SearchQuery(year_from=2020, open_access=True, study_types=("Meta-análise", "Revisão sistemática"), language="pt")
    assert build_query(query) == (
        'HAS_ABSTRACT:y AND PUB_YEAR:[2020 TO 2100] AND OPEN_ACCESS:y AND '
        '(PUB_TYPE:"Meta-Analysis" OR PUB_TYPE:"Systematic Review") AND LANG:por'
    )


def test_user_text_is_parenthesized_and_unbalanced_quotes_are_neutralized():
    assert build_query(SearchQuery(q="metformina")) == "(metformina)"
    assert build_query(SearchQuery(q='"type 2" diabetes')) == '("type 2" diabetes)'
    assert build_query(SearchQuery(q='diabetes "tipo')) == "(diabetes  tipo)"
    assert "\\" not in build_query(SearchQuery(q="a\\b"))


def test_unknown_study_type_and_language_are_ignored():
    assert build_query(SearchQuery(q="x", study_types=("Inventado",), language="zz")) == "(x)"
    assert build_query(SearchQuery(year_to=2010)) == "HAS_ABSTRACT:y AND PUB_YEAR:[1800 TO 2010]"


def test_every_filter_label_maps_to_an_official_label_shown_on_results():
    from extraction import STUDY_TYPE_LABELS

    official = set(STUDY_TYPE_LABELS.values())
    assert set(epmc.STUDY_FILTERS) <= official


# ------------------------------------------------------------------ mapeamento
def test_record_is_mapped_to_a_work():
    work = to_work(RECORD)
    assert work.ref == "31263284" and work.pmid == "31263284" and work.pmcid == "PMC6699990"
    assert work.title == "Supplementation with Akkermansia muciniphila in overweight and obese volunteers: a pilot study"
    assert work.authors == (Author("Depommier", "Clara"), Author("Everard", "A"))
    assert (work.journal, work.year, work.volume, work.issue, work.pages) == ("Nature medicine", 2019, "25", "7", "1096-1103")
    assert work.open_access and work.oa_url == "https://europepmc.org/articles/PMC6699990"  # html antes de pdf
    assert work.study_types == ("Ensaio clínico randomizado",)  # tipos genericos sao omitidos
    assert work.cited_by == 1769 and work.language == "en" and work.source == "Europe PMC"
    assert work.abstract == "Background: Obesity is linked to gut microbiota. Methods: We enrolled 32 volunteers."
    assert work.keywords == ("microbiota", "obesity")


def test_closed_record_has_no_oa_link_and_falls_back_to_mesh_and_author_string():
    record = {"id": "99", "pmid": "99", "title": "Fechado.", "isOpenAccess": "N", "pubYear": "bad", "language": "por",
              "authorString": "Silva J, Souza M.", "citedByCount": "x",
              "fullTextUrlList": {"fullTextUrl": [{"availabilityCode": "S", "url": "https://doi.org/10.1/x"}]},
              "meshHeadingList": {"meshHeading": [{"descriptorName": "Humans"}, {"descriptorName": "Aged"}]}}
    work = to_work(record)
    assert not work.open_access and work.oa_url == "" and work.year is None and work.cited_by == 0
    assert work.language == "pt" and work.keywords == ("Humans", "Aged")
    assert work.authors == (Author("Silva", "J"), Author("Souza", "M"))


def test_ref_prefers_pmid_then_pmcid_then_doi_then_id():
    assert to_work({"pmid": "1", "pmcid": "PMC2", "doi": "10.1/x", "id": "9"}).ref == "1"
    assert to_work({"pmcid": "PMC2", "doi": "10.1/x", "id": "9"}).ref == "PMC2"
    assert to_work({"doi": "10.1/x", "id": "PPR9"}).ref == "10.1/x"
    assert to_work({"id": "PPR9"}).ref == "PPR9"


def test_minimal_record_does_not_crash():
    work = to_work({})
    assert work.title == "Título não informado" and work.authors == () and work.year is None


def test_html_cleaning():
    assert clean_html_text("<h4>Methods:</h4><p>A <b>b</b> &amp; c</p><p>d</p>") == "Methods: A b & c d"
    assert clean_html_text("") == ""


# ------------------------------------------------------------------ busca e get
def _response(payload):
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


@patch("europepmc_catalog.requests.get")
def test_search_sends_paging_sort_and_returns_total(mock_get):
    mock_get.return_value = _response({"hitCount": 1345, "resultList": {"result": [RECORD, RECORD]}})
    result = EuropePmcCatalog().search(SearchQuery(q="metformin", sort="cited", page=3, per_page=5, open_access=True))
    params = mock_get.call_args.kwargs["params"]
    assert params["query"] == "(metformin) AND OPEN_ACCESS:y" and params["sort"] == "CITED desc"
    assert params["page"] == "3" and params["pageSize"] == "5" and params["resultType"] == "core" and params["format"] == "json"
    assert result.total == 1345 and len(result.works) == 2 and result.pages == 269 and result.source == "europepmc"
    assert mock_get.call_args.kwargs["timeout"] == epmc.HTTP_TIMEOUT


@patch("europepmc_catalog.requests.get")
def test_relevance_sort_sends_no_sort_param_and_recent_maps_to_publication_date(mock_get):
    mock_get.return_value = _response({"hitCount": 0, "resultList": {"result": []}})
    EuropePmcCatalog().search(SearchQuery(q="x"))
    assert "sort" not in mock_get.call_args.kwargs["params"]
    EuropePmcCatalog().search(SearchQuery(q="x", sort="recent"))
    assert mock_get.call_args.kwargs["params"]["sort"] == "P_PDATE_D desc"


@pytest.mark.parametrize("failure", [requests.ConnectionError("https://secret-url down"), requests.Timeout("t")])
@patch("europepmc_catalog.requests.get")
def test_network_errors_become_safe_catalog_errors(mock_get, failure):
    mock_get.side_effect = failure
    with pytest.raises(CatalogError) as info:
        EuropePmcCatalog().search(SearchQuery(q="x"))
    assert "secret-url" not in str(info.value) and "indisponível" in str(info.value)


@patch("europepmc_catalog.requests.get")
def test_invalid_json_is_a_catalog_error(mock_get):
    bad = MagicMock()
    bad.raise_for_status.return_value = None
    bad.json.side_effect = ValueError("nao e json")
    mock_get.return_value = bad
    with pytest.raises(CatalogError):
        EuropePmcCatalog().search(SearchQuery(q="x"))


@patch("europepmc_catalog.requests.get")
def test_get_by_pmid_pmcid_and_doi(mock_get):
    mock_get.return_value = _response({"resultList": {"result": [RECORD]}})
    catalog = EuropePmcCatalog()
    assert catalog.get("31263284").title.startswith("Supplementation")
    assert mock_get.call_args.kwargs["params"]["query"] == "EXT_ID:31263284 AND SRC:MED"
    catalog.get("PMC6699990")
    assert mock_get.call_args.kwargs["params"]["query"] == "PMCID:PMC6699990"
    catalog.get("https://doi.org/10.1038/s41591-019-0495-2")
    assert mock_get.call_args.kwargs["params"]["query"] == 'DOI:"10.1038/s41591-019-0495-2"'


@patch("europepmc_catalog.requests.get")
def test_get_returns_none_for_unsupported_refs_without_calling_the_network_and_for_empty_results(mock_get):
    catalog = EuropePmcCatalog()
    assert catalog.get("W2741809807") is None and catalog.get("2301.00001") is None
    mock_get.assert_not_called()
    mock_get.return_value = _response({"resultList": {"result": []}})
    assert catalog.get("33984217") is None


def test_study_type_options_are_the_filter_labels():
    assert EuropePmcCatalog().study_types()[0] == "Ensaio clínico randomizado"
    assert len(EuropePmcCatalog().study_types()) == len(epmc.STUDY_FILTERS)


def test_translated_titles_lose_their_brackets_and_final_period():
    assert to_work({"title": "[Co-manejo da tuberculose e do diabetes: revisão integrativa]."}).title == (
        "Co-manejo da tuberculose e do diabetes: revisão integrativa"
    )
    assert to_work({"title": "Um título [com colchetes] no meio."}).title == "Um título [com colchetes] no meio"


def test_technical_registry_labels_do_not_become_study_type_badges():
    work = to_work({"pubTypeList": {"pubType": ["review-article", "English Abstract", "other", "Journal Article"]}})
    assert work.study_types == ("Revisão",)
    assert to_work({"pubTypeList": {"pubType": ["English Abstract", "Unknown Type"]}}).study_types == ()
