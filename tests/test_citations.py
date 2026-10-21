from unittest.mock import MagicMock, patch

import pytest
import requests

import citations
from citations import Author, CitationMetadata
from domain import NexusError
from prompt_builders import SYS_PROMPT  # noqa: F401  (garante import do pacote)

META = CitationMetadata(
    title="Effect of metformin on outcomes.",
    authors=(Author("Silva", "João Antônio"), Author("Souza", "Maria"), Author("O'Neil", "Ann-Marie")),
    journal="Journal of Testing",
    year="2021",
    volume="12",
    issue="3",
    pages="45-67",
    doi="10.1000/xyz123",
)


def test_abnt_with_three_authors():
    assert citations.format_abnt(META) == (
        "SILVA, J. A.; SOUZA, M.; O'NEIL, A. M. Effect of metformin on outcomes. "
        "Journal of Testing, v. 12, n. 3, p. 45-67, 2021. DOI: 10.1000/xyz123."
    )


def test_abnt_more_than_three_authors_uses_et_al():
    many = CitationMetadata(title="T", authors=tuple(Author(f"Autor{i}", "X") for i in range(5)), journal="J", year="2020")
    assert citations.format_abnt(many).startswith("AUTOR0, X. et al. T.")


def test_abnt_without_authors_starts_with_uppercase_title():
    assert citations.format_abnt(CitationMetadata(title="Um titulo", journal="J", year="2020")).startswith("UM TITULO.")


def test_apa_formats_authors_year_and_italics():
    assert citations.format_apa(META) == (
        "Silva, J. A., Souza, M., & O'Neil, A. M. (2021). Effect of metformin on outcomes. "
        "*Journal of Testing*, *12*(3), 45–67. https://doi.org/10.1000/xyz123"
    )


def test_apa_without_year_uses_sd():
    assert "(s.d.)" in citations.format_apa(CitationMetadata(title="T", authors=(Author("Silva", "A"),)))


def test_vancouver():
    assert citations.format_vancouver(META) == (
        "Silva JA, Souza M, O'Neil AM. Effect of metformin on outcomes. Journal of Testing. "
        "2021;12(3):45-67. doi:10.1000/xyz123"
    )


def test_vancouver_more_than_six_authors():
    meta = CitationMetadata(title="T", authors=tuple(Author(f"A{i}", "B") for i in range(8)), journal="J", year="2020")
    assert "A5 B, et al." in citations.format_vancouver(meta)


def test_missing_fields_are_omitted_not_invented():
    bare = CitationMetadata(title="Somente titulo")
    for formatter in citations.FORMATTERS.values():
        text = formatter(bare)
        assert "None" not in text and "doi" not in text.lower() and "v. " not in text


def test_title_html_and_trailing_period_are_cleaned():
    meta = CitationMetadata(title="A <i>nice</i>  title.", authors=(Author("X", "Y"),), journal="J", year="2020")
    assert "A nice title." in citations.format_vancouver(meta)


def test_unknown_style_is_a_domain_error():
    with pytest.raises(NexusError):
        citations.format_citation(META, "Chicago")


def test_author_initials_handle_hyphens_and_dots():
    assert Author("X", "Ann-Marie J.").initials == ["A", "M", "J"]
    assert Author("X").initials == []


def test_parse_crossref():
    meta = citations.parse_crossref(
        {
            "title": ["T"], "container-title": ["J"], "DOI": "10.1/x", "volume": "5", "issue": "2", "page": "1-9",
            "issued": {"date-parts": [[2019, 3]]},
            "author": [{"family": "Silva", "given": "Ana"}, {"name": "Consortium"}],
        }
    )
    assert meta.year == "2019" and meta.authors == (Author("Silva", "Ana"),) and meta.doi == "10.1/x"


def test_parse_europe_pmc():
    meta = citations.parse_europe_pmc(
        {
            "title": "T", "pubYear": "2020", "pageInfo": "10-20", "doi": "10.1/y",
            "authorList": {"author": [{"lastName": "Lima", "firstName": "Carlos"}, {"lastName": "Dias", "initials": "P"}]},
            "journalInfo": {"volume": "7", "issue": "1", "journal": {"title": "Rev X"}},
        }
    )
    assert meta.journal == "Rev X" and meta.volume == "7" and meta.authors[1] == Author("Dias", "P")


def _json(payload):
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


@patch("citations.requests.get")
def test_fetch_by_doi_uses_crossref(mock_get):
    mock_get.return_value = _json({"message": {"title": ["T"], "DOI": "10.1000/abc"}})
    assert citations.fetch_citation_metadata("https://doi.org/10.1000/abc").title == "T"
    assert mock_get.call_args.args[0].endswith("/works/10.1000/abc")


@patch("citations.requests.get")
def test_fetch_by_pmid_uses_europe_pmc(mock_get):
    mock_get.return_value = _json({"resultList": {"result": [{"title": "T", "pubYear": "2020"}]}})
    assert citations.fetch_citation_metadata("33984217").year == "2020"
    assert mock_get.call_args.kwargs["params"]["query"] == "EXT_ID:33984217"


@patch("citations.requests.get")
def test_fetch_by_pmcid_queries_pmcid_field(mock_get):
    mock_get.return_value = _json({"resultList": {"result": [{"title": "T"}]}})
    citations.fetch_citation_metadata("PMC123456")
    assert mock_get.call_args.kwargs["params"]["query"] == "PMCID:PMC123456"


@patch("citations.requests.get")
def test_fetch_not_found_and_network_errors(mock_get):
    mock_get.return_value = _json({"resultList": {"result": []}})
    with pytest.raises(NexusError, match="não encontrado"):
        citations.fetch_citation_metadata("33984217")
    mock_get.side_effect = requests.ConnectionError("down")
    with pytest.raises(NexusError, match="metadados"):
        citations.fetch_citation_metadata("10.1000/abc")


def test_unsupported_input_asks_for_doi_pmid():
    with pytest.raises(NexusError, match="DOI, PMID ou PMCID"):
        citations.fetch_citation_metadata("2301.00001")


@patch("citations.requests.get")
def test_record_without_title_is_rejected(mock_get):
    mock_get.return_value = _json({"message": {"title": []}})
    with pytest.raises(NexusError, match="não tem título"):
        citations.fetch_citation_metadata("10.1000/abc")
