from unittest.mock import MagicMock, patch

import pytest
import requests

import openalex_catalog as oa
from catalog import CatalogError, SearchQuery
from citations import Author
from openalex_catalog import OpenAlexCatalog, build_filter, split_name, to_work

RECORD = {
    "id": "https://openalex.org/W3197233987",
    "doi": "https://doi.org/10.1093/eurheartj/ehab484",
    "title": "2021 ESC Guidelines on cardiovascular disease prevention in clinical practice",
    "publication_year": 2021, "type": "article", "language": "en", "cited_by_count": 6494,
    "open_access": {"is_oa": True, "oa_status": "bronze", "oa_url": "https://academic.oup.com/x.pdf"},
    "primary_location": {"source": {"display_name": "European Heart Journal"}},
    "authorships": [
        {"author": {"display_name": "Frank L.J. Visseren"}},
        {"author": {"display_name": "Maria de Souza"}},
        {"author": {"display_name": "Madonna"}},
        {"author": {"display_name": ""}},
    ],
    "biblio": {"volume": "42", "issue": "34", "first_page": "3227", "last_page": "3337"},
    "abstract_inverted_index": {"Guidelines": [0], "for": [1], "prevention": [2]},
    "keywords": [{"display_name": "cardiovascular disease prevention"}, {"display_name": "primary prevention"}],
    "ids": {"openalex": "https://openalex.org/W3197233987", "pmid": "https://pubmed.ncbi.nlm.nih.gov/34458905"},
}


def test_name_splitting_handles_particles_and_single_names():
    assert split_name("Frank L.J. Visseren") == Author("Visseren", "Frank L.J.")
    assert split_name("Maria de Souza") == Author("de Souza", "Maria")
    assert split_name("Ana Maria da Silva") == Author("da Silva", "Ana Maria")
    assert split_name("Madonna") == Author("Madonna")


def test_record_is_mapped_to_a_work():
    work = to_work(RECORD)
    assert work.ref == "34458905" and work.pmid == "34458905" and work.doi == "10.1093/eurheartj/ehab484"
    assert work.title.startswith("2021 ESC Guidelines") and work.year == 2021
    assert work.authors == (Author("Visseren", "Frank L.J."), Author("de Souza", "Maria"), Author("Madonna"))
    assert (work.journal, work.volume, work.issue, work.pages) == ("European Heart Journal", "42", "34", "3227-3337")
    assert work.open_access and work.oa_url == "https://academic.oup.com/x.pdf"
    assert work.study_types == ("Artigo",) and work.cited_by == 6494 and work.language == "en"
    assert work.abstract == "Guidelines for prevention" and work.keywords[0] == "cardiovascular disease prevention"
    assert work.source == "OpenAlex"


def test_ref_falls_back_to_doi_then_openalex_id_and_missing_fields_do_not_crash():
    assert to_work({"id": "https://openalex.org/W1", "doi": "https://doi.org/10.1/x"}).ref == "10.1/x"
    assert to_work({"id": "https://openalex.org/W1"}).ref == "W1"
    work = to_work({})
    assert work.title == "Título não informado" and work.authors == () and work.year is None and work.cited_by == 0
    assert to_work({"type": "dataset"}).study_types == ("Conjunto de dados",)
    assert to_work({"type": "paratext"}).study_types == ()


def test_topics_are_used_when_there_are_no_keywords_and_single_page_is_kept():
    work = to_work({"topics": [{"display_name": "Public Health"}], "biblio": {"first_page": "e12", "last_page": "e12"}})
    assert work.keywords == ("Public Health",) and work.pages == "e12"


def test_filter_building():
    query = SearchQuery(year_from=2020, open_access=True, study_types=("Revisão", "Preprint", "Inventado"), language="pt")
    assert build_filter(query) == "publication_year:2020-2100,open_access.is_oa:true,type:review|preprint,language:pt"
    assert build_filter(SearchQuery()) == ""


def test_catalog_requires_an_api_key():
    with pytest.raises(ValueError):
        OpenAlexCatalog("")


def _response(payload=None, status=200):
    response = MagicMock()
    response.status_code = status
    response.json.return_value = payload or {}
    if status >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(str(status))
    else:
        response.raise_for_status.return_value = None
    return response


@patch("openalex_catalog.requests.get")
def test_search_sends_key_filters_sort_and_paging(mock_get):
    mock_get.return_value = _response({"meta": {"count": 50229}, "results": [RECORD]})
    result = OpenAlexCatalog("chave-secreta", mailto="time@exemplo.org").search(
        SearchQuery(q="metformin", open_access=True, sort="cited", page=2, per_page=5, language="en")
    )
    params = mock_get.call_args.kwargs["params"]
    assert params["search"] == "metformin"
    assert params["filter"] == "title_and_abstract.search:metformin,open_access.is_oa:true,language:en"
    assert params["sort"] == "cited_by_count:desc" and params["page"] == "2" and params["per-page"] == "5"
    assert params["api_key"] == "chave-secreta" and params["mailto"] == "time@exemplo.org"
    assert result.total == 50229 and len(result.works) == 1 and result.source == "openalex"


@patch("openalex_catalog.requests.get")
def test_empty_query_omits_search_and_relevance_sends_no_sort(mock_get):
    mock_get.return_value = _response({"meta": {"count": 0}, "results": []})
    OpenAlexCatalog("k").search(SearchQuery(year_from=2020))
    params = mock_get.call_args.kwargs["params"]
    assert "search" not in params and "sort" not in params and "mailto" not in params


@pytest.mark.parametrize("status", [402, 403, 429])
@patch("openalex_catalog.requests.get")
def test_budget_and_key_errors_become_a_friendly_message_without_leaking_the_key(mock_get, status):
    mock_get.return_value = _response(status=status)
    with pytest.raises(CatalogError) as info:
        OpenAlexCatalog("chave-secreta").search(SearchQuery(q="x"))
    assert "limite" in str(info.value) and "chave-secreta" not in str(info.value)


@pytest.mark.parametrize("failure", [requests.ConnectionError("https://api...?api_key=chave-secreta"), requests.Timeout()])
@patch("openalex_catalog.requests.get")
def test_network_errors_never_expose_the_request_url(mock_get, failure):
    mock_get.side_effect = failure
    with pytest.raises(CatalogError) as info:
        OpenAlexCatalog("chave-secreta").search(SearchQuery(q="x"))
    assert "chave-secreta" not in str(info.value) and "indisponível" in str(info.value)


@patch("openalex_catalog.requests.get")
def test_server_error_and_invalid_json_are_catalog_errors(mock_get):
    mock_get.return_value = _response(status=500)
    with pytest.raises(CatalogError, match="falhou"):
        OpenAlexCatalog("k").search(SearchQuery(q="x"))
    bad = _response()
    bad.json.side_effect = ValueError("nao e json")
    mock_get.return_value = bad
    with pytest.raises(CatalogError):
        OpenAlexCatalog("k").search(SearchQuery(q="x"))


@patch("openalex_catalog.requests.get")
def test_get_resolves_openalex_id_pmid_and_doi(mock_get):
    mock_get.return_value = _response(RECORD)
    catalog = OpenAlexCatalog("k")
    assert catalog.get("W3197233987").doi == "10.1093/eurheartj/ehab484"
    assert mock_get.call_args.args[0].endswith("/works/W3197233987")
    catalog.get("34458905")
    assert mock_get.call_args.args[0].endswith("/works/pmid:34458905")
    catalog.get("10.1093/eurheartj/ehab484")
    assert mock_get.call_args.args[0].endswith("/works/doi%3A10.1093%2Feurheartj%2Fehab484") or "doi:10.1093" in mock_get.call_args.args[0]


@patch("openalex_catalog.requests.get")
def test_get_returns_none_for_404_and_unsupported_refs_without_calling_the_network(mock_get):
    catalog = OpenAlexCatalog("k")
    assert catalog.get("PMC123456") is None and catalog.get("2301.00001") is None and catalog.get("texto") is None
    mock_get.assert_not_called()
    mock_get.return_value = _response(status=404)
    assert catalog.get("W1") is None


def test_study_type_options():
    assert OpenAlexCatalog("k").study_types() == tuple(oa.TYPE_FILTERS)


def test_query_text_is_restricted_to_title_and_abstract_and_cannot_break_the_filter_syntax():
    assert build_filter(SearchQuery(q="engenharia civil")) == "title_and_abstract.search:engenharia civil"
    hostile = build_filter(SearchQuery(q="a,open_access.is_oa:false|b"))
    assert hostile == "title_and_abstract.search:a open_access.is_oa:false b"
    assert "," not in hostile and "|" not in hostile  # nao injeta outros filtros
    assert build_filter(SearchQuery(q=" , | ")) == ""
