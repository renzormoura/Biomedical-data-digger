import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from conftest import make_response

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "biomedical-article-summariser"))

import article_services


class DetectInputTypeTest(unittest.TestCase):
    def test_existing_id_formats_still_detected(self):
        cases = {
            "33984217": "pmid",
            "PMC8234567": "pmcid",
            "10.1038/s41586-021-03819-2": "doi",
            "2301.00001": "arxiv",
            "W2741809807": "openalex",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                input_type, _ = article_services.detect_input_type(value)
                self.assertEqual(input_type, expected)

    def test_known_scientific_urls_still_detected(self):
        cases = {
            "https://pubmed.ncbi.nlm.nih.gov/33984217/": "pmid",
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC8234567/": "pmcid",
            "https://doi.org/10.1038/s41586-021-03819-2": "doi",
            "https://arxiv.org/abs/2301.00001": "arxiv",
            "https://openalex.org/W2741809807": "openalex",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                input_type, _ = article_services.detect_input_type(value)
                self.assertEqual(input_type, expected)

    def test_google_scholar_search_link(self):
        input_type, value = article_services.detect_input_type(
            "https://scholar.google.com/scholar?q=metformin+diabetes+remission"
        )
        self.assertEqual(input_type, "google_scholar")
        self.assertIn("q=metformin", value)

    def test_google_scholar_cluster_link(self):
        input_type, value = article_services.detect_input_type(
            "https://scholar.google.com/scholar?cluster=1234567890"
        )
        self.assertEqual(input_type, "google_scholar")
        self.assertIn("cluster=1234567890", value)

    def test_doi_embedded_in_publisher_url(self):
        input_type, value = article_services.detect_input_type(
            "https://www.nature.com/articles/s41586-021-03819-2"
        )
        # URL de editora sem DOI visivel deve cair no fallback generico
        self.assertEqual(input_type, "generic_url")

        input_type, value = article_services.detect_input_type(
            "https://link.springer.com/article/10.1007/s00125-020-05232-5"
        )
        self.assertEqual(input_type, "doi")
        self.assertEqual(value, "10.1007/s00125-020-05232-5")

    def test_generic_publisher_url(self):
        input_type, value = article_services.detect_input_type(
            "https://www.sciencedirect.com/science/article/pii/S0140673620306247"
        )
        self.assertEqual(input_type, "generic_url")
        self.assertTrue(value.startswith("https://"))

    def test_url_without_scheme_is_accepted(self):
        input_type, value = article_services.detect_input_type(
            "www.nature.com/articles/s41586-021-03819-2"
        )
        self.assertEqual(input_type, "generic_url")
        self.assertTrue(value.startswith("https://"))

    def test_plain_text_is_not_treated_as_url(self):
        input_type, _ = article_services.detect_input_type("isso e um texto qualquer sem link")
        self.assertEqual(input_type, "unknown")


class GoogleScholarResolutionTest(unittest.TestCase):
    @patch("article_services._search_europe_pmc")
    def test_scholar_search_query_resolves_via_title_lookup(self, mock_search):
        mock_search.return_value = [
            {
                "title": "Metformin and diabetes outcomes",
                "abstractText": "A study about metformin.",
                "pmid": "12345678",
                "journalTitle": "Journal",
                "pubYear": 2024,
                "doi": "10.1000/test",
                "citedByCount": 10,
                "source": "MED",
            }
        ]

        title, abstract, source = article_services.resolve_article(
            "https://scholar.google.com/scholar?q=metformin+diabetes"
        )

        self.assertEqual(title, "Metformin and diabetes outcomes")
        self.assertEqual(abstract, "A study about metformin.")
        self.assertEqual(source, "Google Academico")

    @patch("article_services.fetch_from_generic_url")
    def test_scholar_result_link_fetches_target_page(self, mock_fetch):
        mock_fetch.return_value = ("Article title", "Article abstract")

        title, abstract, source = article_services.resolve_article(
            "https://scholar.google.com/scholar_url?url=https%3A%2F%2Fexample.com%2Fpaper"
        )

        self.assertEqual(title, "Article title")
        self.assertEqual(abstract, "Article abstract")
        self.assertEqual(source, "Google Academico")
        mock_fetch.assert_called_once_with("https://example.com/paper")

    @patch("article_services.requests.get")
    def test_scholar_cluster_page_uses_first_result(self, mock_get):
        mock_get.return_value = make_response(
            b"<html><body>"
            b"<h3 class='gs_rt'><a href='https://example.com/paper'>Clustered article</a></h3>"
            b"</body></html>"
        )

        with patch.object(article_services, "_title_lookup", return_value=("Clustered article", "")), \
             patch.object(article_services, "fetch_from_generic_url", return_value=("Clustered article", "Clustered abstract")) as mock_fetch:
            title, abstract, source = article_services.resolve_article(
                "https://scholar.google.com/scholar?cluster=1234567890"
            )

        self.assertEqual(title, "Clustered article")
        self.assertEqual(abstract, "Clustered abstract")
        self.assertEqual(source, "Google Academico")
        mock_fetch.assert_called_once_with("https://example.com/paper")


class GenericUrlResolutionTest(unittest.TestCase):
    @patch("article_services.requests.get")
    def test_generic_url_extracts_meta_tags(self, mock_get):
        mock_get.return_value = make_response(
            b"<html><head>"
            b"<meta name='citation_title' content='Meta title'>"
            b"<meta name='citation_abstract' content='Meta abstract text.'>"
            b"</head><body><p>Body text.</p></body></html>"
        )

        title, abstract, source = article_services.resolve_article(
            "https://www.example-journal.com/article/123"
        )

        self.assertEqual(title, "Meta title")
        self.assertEqual(abstract, "Meta abstract text.")
        self.assertEqual(source, "Pagina do artigo")

    @patch("article_services.requests.get")
    def test_generic_url_falls_back_to_doi_in_page(self, mock_get):
        mock_get.return_value = make_response(
            b"<html><head>"
            b"<meta name='citation_doi' content='10.1000/fallback-doi'>"
            b"</head><body><p>Body text.</p></body></html>"
        )

        with patch.object(article_services, "fetch_by_doi", return_value=("DOI title", "DOI abstract")):
            title, abstract, _ = article_services.resolve_article(
                "https://www.example-journal.com/article/123"
            )

        self.assertEqual(title, "DOI title")
        self.assertEqual(abstract, "DOI abstract")


class BlockedPageFallbackTest(unittest.TestCase):
    def test_extract_identifier_from_science_direct_pii(self):
        id_type, identifier = article_services._extract_identifier_from_url(
            "https://www.sciencedirect.com/science/article/pii/S0378778801001372"
        )
        self.assertEqual(id_type, "pii")
        self.assertEqual(identifier, "S0378778801001372")

    def test_doi_suffix_from_publisher_page_is_stripped(self):
        # /full e /fulltext sao vistas de pagina, nao parte do DOI
        cases = {
            "https://www.frontiersin.org/articles/10.3389/fimmu.2021.650095/full":
                "10.3389/fimmu.2021.650095",
            "https://doi.org/10.3389/fimmu.2021.650095/full":
                "10.3389/fimmu.2021.650095",
            "https://link.springer.com/article/10.1007/s00125-020-05232-5":
                "10.1007/s00125-020-05232-5",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                input_type, value = article_services.detect_input_type(url)
                self.assertEqual(input_type, "doi")
                self.assertEqual(value, expected)
                id_type, identifier = article_services._extract_identifier_from_url(url)
                self.assertEqual((id_type, identifier), ("doi", expected))

    def test_preprint_version_suffix_is_stripped(self):
        input_type, value = article_services.detect_input_type(
            "https://www.medrxiv.org/content/10.1101/2020.03.04.20031120v1"
        )
        self.assertEqual(input_type, "doi")
        self.assertEqual(value, "10.1101/2020.03.04.20031120")

    def test_doi_with_query_string_is_stripped(self):
        input_type, value = article_services.detect_input_type(
            "https://doi.org/10.1038/s41586-021-03819-2?utm_source=twitter"
        )
        self.assertEqual(input_type, "doi")
        self.assertEqual(value, "10.1038/s41586-021-03819-2")

    def test_elsevier_pii_with_parentheses_is_extracted(self):
        cases = {
            "https://www.thelancet.com/journals/lancet/article/PIIS0140-6736(20)30183-5/fulltext":
                "S0140673620301835",
            "https://www.cell.com/cell/fulltext/S0092-8674(20)30183-5":
                "S0092867420301835",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                id_type, identifier = article_services._extract_identifier_from_url(url)
                self.assertEqual(id_type, "pii")
                self.assertEqual(identifier, expected)

    def test_bare_pii_outside_pii_path_is_extracted(self):
        id_type, identifier = article_services._extract_identifier_from_url(
            "https://www.cell.com/cell/fulltext/S0092867426009335"
        )
        self.assertEqual(id_type, "pii")
        self.assertEqual(identifier, "S0092867426009335")

    def test_bmj_article_url_derives_doi(self):
        id_type, identifier = article_services._extract_identifier_from_url(
            "https://www.bmj.com/content/374/bmj-2026-100739"
        )
        self.assertEqual(id_type, "doi")
        self.assertEqual(identifier, "10.1136/bmj-2026-100739")

    def test_short_meta_description_is_not_used_as_abstract(self):
        # "Diabetologia -" (14 chars) nao e um resumo
        self.assertFalse(
            len("Diabetologia -") >= article_services.MIN_ABSTRACT_CHARS
        )

    def test_extract_doi_from_url_path(self):
        id_type, identifier = article_services._extract_identifier_from_url(
            "https://link.springer.com/article/10.1007/s00125-020-05232-5"
        )
        self.assertEqual(id_type, "doi")
        self.assertEqual(identifier, "10.1007/s00125-020-05232-5")

    @patch("article_services.requests.get")
    @patch.object(article_services, "fetch_by_doi", return_value=("Artigo nao encontrado via DOI", ""))
    def test_blocked_page_resolves_via_crossref_alternative_id(self, mock_doi, mock_get):
        # 1a chamada: Crossref pre-check (titulo sem abstract) -> continua para a pagina
        # 2a chamada: pagina bloqueada com 403 -> fallback final usa o Crossref
        crossref_precheck = MagicMock()
        crossref_precheck.raise_for_status.return_value = None
        crossref_precheck.json.return_value = {
            "message": {"items": [{"title": ["On the energy consumption in residential buildings"], "abstract": ""}]}
        }
        blocked = make_response(b"", status=403)
        crossref_fallback = MagicMock()
        crossref_fallback.raise_for_status.return_value = None
        crossref_fallback.json.return_value = {
            "message": {
                "items": [
                    {
                        "title": ["On the energy consumption in residential buildings"],
                        "abstract": "This is the abstract text.",
                    }
                ]
            }
        }
        mock_get.side_effect = [crossref_precheck, blocked, crossref_fallback]

        title, abstract = article_services.fetch_from_generic_url(
            "https://www.sciencedirect.com/science/article/pii/S0378778801001372"
        )

        self.assertEqual(title, "On the energy consumption in residential buildings")
        self.assertEqual(abstract, "This is the abstract text.")

    @patch("article_services.requests.get")
    def test_doi_in_url_tries_doi_pipeline_first(self, mock_get):
        # Sem requests reais: se o DOI resolver logo no inicio, nao acessa a pagina
        with patch.object(article_services, "fetch_by_doi", return_value=("DOI title", "DOI abstract")) as mock_doi:
            title, abstract = article_services.fetch_from_generic_url(
                "https://link.springer.com/article/10.1007/s00125-020-05232-5"
            )
        self.assertEqual(title, "DOI title")
        mock_doi.assert_called_once_with("10.1007/s00125-020-05232-5")


class SameArticleTest(unittest.TestCase):
    def test_rejects_abstract_from_a_different_article(self):
        self.assertFalse(
            article_services._same_article(
                "Offline: Can time be tamed?",
                "Emotional violence by teachers toward students",
            )
        )
        self.assertFalse(
            article_services._same_article(
                "Comment to: Grassi G, Dell'oro R, Quarti-Trevano F et al (2005)",
                "Waist Circumference as a potential indicator",
            )
        )

    def test_accepts_same_article_with_minor_title_variation(self):
        self.assertTrue(
            article_services._same_article(
                "Highly accurate protein structure prediction with AlphaFold",
                "Highly accurate protein structure prediction with AlphaFold",
            )
        )
        self.assertTrue(
            article_services._same_article(
                "Quadrivalent human papillomavirus vaccination",
                "Effectiveness of quadrivalent human papillomavirus vaccination",
            )
        )

    def test_empty_titles_never_match(self):
        self.assertFalse(article_services._same_article("", "Any title here"))
        self.assertFalse(article_services._same_article("Any title here", ""))


class TitleLookupFallbackTest(unittest.TestCase):
    @patch("article_services._search_openalex")
    @patch("article_services._search_semantic_scholar")
    @patch("article_services._search_europe_pmc")
    def test_title_lookup_prefers_result_with_abstract(self, mock_pmc, mock_s2, mock_openalex):
        mock_pmc.return_value = [{"title": "PMC result", "abstractText": ""}]
        mock_s2.return_value = [{"title": "S2 result"}]
        mock_openalex.return_value = [
            {
                "title": "OpenAlex result",
                "abstract_inverted_index": {"Study": [0], "about": [1], "cancer": [2]},
            }
        ]

        title, abstract = article_services._title_lookup("cancer study")

        self.assertEqual(title, "OpenAlex result")
        self.assertEqual(abstract, "Study about cancer")

    @patch("article_services._search_openalex")
    @patch("article_services._search_semantic_scholar")
    @patch("article_services._search_europe_pmc")
    def test_title_lookup_survives_source_failure(self, mock_pmc, mock_s2, mock_openalex):
        mock_pmc.side_effect = RuntimeError("source down")
        mock_s2.return_value = [{"title": "S2 result"}]
        mock_openalex.return_value = []

        title, abstract = article_services._title_lookup("anything")

        self.assertEqual(title, "S2 result")
        self.assertEqual(abstract, "")


if __name__ == "__main__":
    unittest.main()

