"""Fetchers por fonte (Europe PMC, DOI, arXiv, OpenAlex, Semantic Scholar) com HTTP simulado."""

from unittest.mock import MagicMock, patch

import pytest
import requests
from bs4 import BeautifulSoup

import article_services as svc


def json_response(payload, status=200):
    response = MagicMock()
    response.status_code = status
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def http_error():
    response = MagicMock()
    response.raise_for_status.side_effect = requests.HTTPError("500")
    return response


PMC_XML = b"""<article><front><article-meta><title-group><article-title>PMC Title</article-title></title-group>
<abstract><p>First paragraph.</p><p>Second [1] paragraph.</p></abstract></article-meta></front>
<body><sec sec-type="methods"><title>Methods</title><p>We did things.</p></sec>
<sec><title>Custom Part</title><p>Extra text.</p></sec><sec><p>no title</p></sec></body></article>"""


class TestXmlParsing:
    def test_abstract_and_title(self):
        soup = BeautifulSoup(PMC_XML, "lxml-xml")
        title, abstract = svc.fetch_article_abstract(soup)
        assert title == "PMC Title"
        assert abstract == "First paragraph. Second paragraph."

    def test_missing_soup_and_missing_abstract(self):
        assert svc.fetch_article_abstract(None) == ("No XML found", "")
        assert svc.fetch_article_abstract(BeautifulSoup(b"<a/>", "lxml-xml"))[1] == ""

    def test_full_text_sections_are_labeled(self):
        title, text = svc.fetch_full_text(BeautifulSoup(PMC_XML, "lxml-xml"))
        assert title == "PMC Title"
        assert "**Metodos:**" in text and "**Custom Part:**" in text
        assert "no title" not in text

    def test_full_text_falls_back_to_abstract_and_none(self):
        only_abstract = BeautifulSoup(b"<article><abstract><p>Only abstract.</p></abstract></article>", "lxml-xml")
        assert svc.fetch_full_text(only_abstract)[1] == "Only abstract."
        assert svc.fetch_full_text(None) == ("No XML found", "")

    @patch("article_services.requests.get")
    def test_get_xml_from_url_returns_none_on_request_error(self, mock_get):
        mock_get.side_effect = requests.ConnectionError("down")
        assert svc.get_xml_from_url("https://www.ebi.ac.uk/x") is None
        assert mock_get.call_args.kwargs["timeout"] == svc.HTTP_TIMEOUT


class TestPmid:
    @patch("article_services.requests.get")
    def test_found(self, mock_get):
        mock_get.return_value = json_response(
            {"resultList": {"result": [{"title": "Trial", "abstractText": "Some [3] abstract."}]}}
        )
        assert svc.get_abstract_from_pmid("33984217") == ("Trial", "Some abstract.")
        assert mock_get.call_args.kwargs["timeout"] == svc.HTTP_TIMEOUT

    @patch("article_services.requests.get")
    def test_not_found(self, mock_get):
        mock_get.return_value = json_response({"resultList": {"result": []}})
        assert svc.get_abstract_from_pmid("1") == ("Artigo nao encontrado", "")


class TestDoi:
    @patch("article_services.requests.get")
    def test_semantic_scholar_first(self, mock_get):
        mock_get.return_value = json_response({"title": "S2 title", "abstract": "S2 abstract"})
        assert svc.fetch_by_doi("10.1/x") == ("S2 title", "S2 abstract")
        assert mock_get.call_count == 1

    @patch("article_services.requests.get")
    def test_falls_back_to_crossref_with_jats_stripped(self, mock_get):
        mock_get.side_effect = [
            json_response({"title": "t", "abstract": None}),
            json_response({"message": {"title": ["CR title"], "abstract": "<jats:p>Cross abstract</jats:p>"}}),
        ]
        title, abstract = svc.fetch_by_doi("10.1/x")
        assert title == "CR title" and abstract == "Cross abstract"

    @patch("article_services.requests.get")
    def test_all_sources_fail(self, mock_get):
        mock_get.side_effect = requests.ConnectionError("down")
        assert svc.fetch_by_doi("10.1/x") == ("Artigo nao encontrado via DOI", "")


class TestArxivOpenalexS2:
    @patch("article_services.requests.get")
    def test_arxiv(self, mock_get):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.content = b"<feed><entry><title> A  title </title><summary>An abstract.</summary></entry></feed>"
        mock_get.return_value = response
        assert svc.fetch_by_arxiv("2301.00001v2") == ("A title", "An abstract.")
        assert "id_list=2301.00001" in mock_get.call_args.args[0]

    @patch("article_services.requests.get")
    def test_arxiv_errors_are_reported_in_title(self, mock_get):
        mock_get.side_effect = requests.ConnectionError("down")
        title, abstract = svc.fetch_by_arxiv("2301.00001")
        assert title.startswith("Erro ao buscar no arXiv") and abstract == ""

    @patch("article_services.requests.get")
    def test_openalex_rebuilds_inverted_index(self, mock_get):
        mock_get.return_value = json_response(
            {"title": "OA", "abstract_inverted_index": {"Hello": [0], "world": [1], "again": [2]}}
        )
        assert svc.fetch_by_openalex("W1") == ("OA", "Hello world again")

    @patch("article_services.requests.get")
    def test_openalex_without_abstract_and_error(self, mock_get):
        mock_get.return_value = json_response({"title": "OA", "abstract_inverted_index": None})
        assert svc.fetch_by_openalex("W1") == ("OA", "")
        mock_get.return_value = http_error()
        assert svc.fetch_by_openalex("W1")[0].startswith("Erro ao buscar no OpenAlex")

    @patch("article_services.requests.get")
    def test_semantic_scholar(self, mock_get):
        mock_get.return_value = json_response({"title": "S2", "abstract": "Abs"})
        assert svc.fetch_by_semantic_scholar("a" * 40) == ("S2", "Abs")
        mock_get.return_value = http_error()
        assert svc.fetch_by_semantic_scholar("a" * 40)[0].startswith("Erro ao buscar no Semantic Scholar")


class TestResolveArticleDispatch:
    @pytest.mark.parametrize(
        "raw,fetcher",
        [
            ("33984217", "get_abstract_from_pmid"),
            ("2301.00001", "fetch_by_arxiv"),
            ("W2741809807", "fetch_by_openalex"),
        ],
    )
    def test_dispatches_to_matching_fetcher(self, raw, fetcher):
        with patch.object(svc, fetcher, return_value=("T", "A")) as mocked:
            assert svc.resolve_article(raw)[:2] == ("T", "A")
        mocked.assert_called_once()

    def test_pmcid_uses_europe_pmc_xml(self):
        soup = BeautifulSoup(PMC_XML, "lxml-xml")
        with patch.object(svc, "get_xml_from_url", return_value=soup) as mocked:
            title, abstract, source = svc.resolve_article("pmc123456")
        assert title == "PMC Title" and "Europe PMC" in source
        assert "PMC123456" in mocked.call_args.args[0]

    def test_doi_without_abstract_tries_publisher_page(self):
        with patch.object(svc, "fetch_by_doi", return_value=("T", "")), patch.object(
            svc, "fetch_from_generic_url", return_value=("Page", "Page abstract")
        ) as page:
            assert svc.resolve_article("10.1000/abc")[:2] == ("Page", "Page abstract")
        assert page.call_args.kwargs == {"resolve_doi": False}

    def test_unrecognized_input_raises(self):
        with pytest.raises(ValueError):
            svc.resolve_article("just some words here")


class TestSearchEdgeCases:
    def test_blank_keyword_returns_empty(self):
        assert svc.search_reliable_articles("   ") == []

    def test_all_sources_failing_raises_runtime_error(self):
        boom = MagicMock(side_effect=requests.ConnectionError("down"))
        with patch.multiple(
            svc, _search_europe_pmc=boom, _search_openalex=boom, _search_semantic_scholar=boom,
            _search_crossref=boom, _search_arxiv=boom,
        ), pytest.raises(RuntimeError, match="Nenhuma fonte"):
            svc.search_reliable_articles("sepsis")

    def test_one_failing_source_does_not_hide_the_others(self):
        boom = MagicMock(side_effect=requests.ConnectionError("down"))
        ok = MagicMock(return_value=[{"title": "T", "pmid": "1", "journalTitle": "J", "pubYear": 2024, "citedByCount": 3}])
        empty = MagicMock(return_value=[])
        with patch.multiple(
            svc, _search_europe_pmc=ok, _search_openalex=boom, _search_semantic_scholar=empty,
            _search_crossref=empty, _search_arxiv=empty,
        ):
            assert len(svc.search_reliable_articles("sepsis")) == 1

    @pytest.mark.parametrize(
        "title,area,expected",
        [("A flaw in the design", "Direito e Politicas Publicas", False), ("Law and society", "Direito e Politicas Publicas", True)],
    )
    def test_area_keywords_match_word_starts_only(self, title, area, expected):
        assert svc._area_matches(title, "", area) is expected

    def test_title_lookup_without_any_title_does_not_crash(self):
        with patch.object(svc, "_search_europe_pmc", return_value=[{}]), patch.object(
            svc, "_search_semantic_scholar", return_value=[]
        ), patch.object(svc, "_search_openalex", return_value=[]):
            title, abstract = svc._title_lookup("something")
        assert title.startswith("Nenhum resultado") and abstract == ""
