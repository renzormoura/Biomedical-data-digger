from unittest.mock import MagicMock, patch

import requests

import europepmc
from europepmc import EuropePmcRecord, parse_record

CORE = {
    "pubTypeList": {"pubType": ["Journal Article", "Randomized Controlled Trial"]},
    "keywordList": {"keyword": ["metformin", "diabetes"]},
    "meshHeadingList": {"meshHeading": [{"descriptorName": "Metformin"}, {"descriptorName": "Aged"}]},
    "grantsList": {"grant": [{"agency": "NIH"}, {"agency": "NIH"}, {"agency": "CNPq"}]},
    "isOpenAccess": "Y",
    "citedByCount": 42,
    "journalTitle": "Diabetes Care",
    "pubYear": "2024",
    "language": "eng",
}


def test_parse_record_extracts_official_fields():
    record = parse_record(CORE)
    assert record.pub_types == ("Journal Article", "Randomized Controlled Trial")
    assert record.keywords == ("metformin", "diabetes") and record.mesh_terms == ("Metformin", "Aged")
    assert record.funders == ("NIH", "CNPq")  # sem duplicatas
    assert record.open_access is True and record.cited_by == 42
    assert (record.journal, record.year, record.language) == ("Diabetes Care", "2024", "eng")


def test_parse_record_is_tolerant_of_missing_or_odd_shapes():
    assert parse_record({}) == EuropePmcRecord()
    odd = parse_record({"pubTypeList": {"pubType": "Review"}, "isOpenAccess": "N", "citedByCount": "7",
                        "journalInfo": {"journal": {"title": "J Info"}}, "meshHeadingList": {"meshHeading": ["x"]}})
    assert odd.pub_types == ("Review",) and odd.open_access is False and odd.cited_by == 7
    assert odd.journal == "J Info" and odd.mesh_terms == ()
    assert parse_record({"isOpenAccess": "?", "citedByCount": "abc"}).open_access is None
    assert parse_record({"citedByCount": "abc"}).cited_by is None


def _response(payload):
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


@patch("europepmc.requests.get")
def test_fetch_uses_the_right_query_per_identifier(mock_get):
    mock_get.return_value = _response({"resultList": {"result": [CORE]}})
    assert europepmc.fetch_record("33984217").year == "2024"
    assert mock_get.call_args.kwargs["params"]["query"] == "EXT_ID:33984217 AND SRC:MED"
    europepmc.fetch_record("PMC123456")
    assert mock_get.call_args.kwargs["params"]["query"] == "PMCID:PMC123456"
    europepmc.fetch_record("https://doi.org/10.1000/abc")
    assert mock_get.call_args.kwargs["params"]["query"] == 'DOI:"10.1000/abc"'
    assert mock_get.call_args.kwargs["timeout"] == europepmc.HTTP_TIMEOUT


@patch("europepmc.requests.get")
def test_fetch_returns_none_for_unsupported_ids_without_calling_the_network(mock_get):
    assert europepmc.fetch_record("2301.00001") is None  # arXiv
    assert europepmc.fetch_record("texto qualquer") is None
    mock_get.assert_not_called()


@patch("europepmc.requests.get")
def test_fetch_is_best_effort_on_failures(mock_get):
    mock_get.side_effect = requests.ConnectionError("down")
    assert europepmc.fetch_record("33984217") is None
    mock_get.side_effect = None
    mock_get.return_value = _response({"resultList": {"result": []}})
    assert europepmc.fetch_record("33984217") is None
    bad = MagicMock()
    bad.raise_for_status.return_value = None
    bad.json.side_effect = ValueError("not json")
    mock_get.return_value = bad
    assert europepmc.fetch_record("33984217") is None
