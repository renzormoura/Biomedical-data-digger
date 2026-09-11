import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "biomedical-article-summariser"))

import article_services


class SearchReliableArticlesTest(unittest.TestCase):
    @patch("article_services.requests.get")
    def test_search_reliable_articles_returns_ranked_results(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "resultList": {
                "result": [
                    {
                        "title": "Effect of metformin on type 2 diabetes outcomes",
                        "pmid": "34567890",
                        "source": "MED",
                        "journalTitle": "New England Journal of Medicine",
                        "pubYear": 2024,
                        "doi": "10.1056/NEJMoa2401234",
                        "citedByCount": 120,
                        "isOpenAccess": True,
                    },
                    {
                        "title": "Clinical predictors of diabetes remission",
                        "pmid": "29876543",
                        "source": "MED",
                        "journalTitle": "Lancet Diabetes & Endocrinology",
                        "pubYear": 2016,
                        "doi": "10.1016/S2213-8587(16)00012-8",
                        "citedByCount": 40,
                        "isOpenAccess": False,
                    },
                    {
                        "title": "Diet and lifestyle interventions in diabetes",
                        "pmid": "31876543",
                        "source": "MED",
                        "journalTitle": "BMJ",
                        "pubYear": 2019,
                        "doi": "10.1136/bmj.l1234",
                        "citedByCount": 18,
                        "isOpenAccess": True,
                    },
                ]
            }
        }

        results = article_services.search_reliable_articles("diabetes mellitus", limit=3, area="Endocrinologia")

        self.assertEqual(len(results), 3)
        self.assertIn("title", results[0])
        self.assertIn("pmid", results[0])
        self.assertIn("reliability", results[0])
        self.assertIn("reliability_score", results[0])
        self.assertIn("PubMed / Europe PMC", results[0]["reliability"])

    def test_search_combines_supported_sources(self):
        with patch.object(article_services, "_search_europe_pmc", return_value=[
            {"title": "Europe PMC article", "pmid": "10000001", "journalTitle": "Journal", "pubYear": 2024, "citedByCount": 10, "source": "MED"},
        ]), patch.object(article_services, "_search_openalex", return_value=[
            {"id": "https://openalex.org/W1", "title": "OpenAlex article", "publication_year": 2023, "doi": "https://doi.org/10.1000/openalex", "cited_by_count": 20, "primary_location": {"source": {"display_name": "OpenAlex Journal"}}},
        ]), patch.object(article_services, "_search_semantic_scholar", return_value=[
            {"paperId": "semantic-1", "title": "Semantic Scholar article", "year": 2022, "venue": "Semantic Journal", "externalIds": {}, "citationCount": 30},
        ]), patch.object(article_services, "_search_crossref", return_value=[
            {"title": ["Crossref article"], "DOI": "10.1000/crossref", "published": {"date-parts": [[2021]]}, "container-title": ["Crossref Journal"], "is-referenced-by-count": 40},
        ]), patch.object(article_services, "_search_arxiv", return_value=[
            article_services.bs("<entry><id>https://arxiv.org/abs/2401.00001</id><title>arXiv article</title><published>2020-01-01</published></entry>", "lxml-xml").find("entry"),
        ]):
            results = article_services.search_reliable_articles("diabetes", limit=10)

        self.assertEqual({item["source"] for item in results}, {"MED", "OPENALEX", "SEMANTIC_SCHOLAR", "CROSSREF", "ARXIV"})
        self.assertEqual(len(results), 5)


if __name__ == "__main__":
    unittest.main()
