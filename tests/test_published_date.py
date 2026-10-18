"""Data de publicacao exata (AAAA-MM-DD) lida de cada fonte, usada para decidir o que e um artigo novo."""

from xml.etree import ElementTree

import pytest

import arxiv_catalog
import europepmc_catalog
import openaire_catalog
import openalex_catalog
import pubmed_catalog
from catalog import Work, iso_date


@pytest.mark.parametrize("raw,expected", [
    ("2026-10-16", "2026-10-16"), ("2026-10-16T04:05:06Z", "2026-10-16"), ("2026-10", "2026-10"),
    ("2026-02-30", ""), ("2026-13-01", ""), ("2026", ""), ("", ""), (None, ""), ("ontem", ""),
])
def test_iso_date_accepts_only_real_dates(raw, expected):
    assert iso_date(raw) == expected


def test_work_roundtrip_keeps_published_and_sanitizes_stored_value():
    work = Work(ref="1", title="T", published="2026-10-16")
    assert Work.from_dict(work.to_dict()).published == "2026-10-16"
    assert Work.from_dict({"ref": "1", "published": "lixo"}).published == ""
    assert Work.from_dict({"ref": "1"}).published == ""  # dados salvos antes deste campo continuam abrindo


def test_europepmc_reads_first_publication_date():
    work = europepmc_catalog.to_work({"id": "1", "pmid": "1", "title": "T", "pubYear": "2026", "firstPublicationDate": "2026-07-13"})
    assert work.published == "2026-07-13" and work.year == 2026


def test_openalex_reads_publication_date_and_requests_the_field():
    assert "publication_date" in openalex_catalog.SELECT
    work = openalex_catalog.to_work({"id": "https://openalex.org/W1", "title": "T", "publication_year": 2026, "publication_date": "2026-09-03"})
    assert work.published == "2026-09-03"


def test_arxiv_reads_submission_date():
    ns = 'xmlns="http://www.w3.org/2005/Atom"'
    entry = ElementTree.fromstring(
        f'<entry {ns}><id>http://arxiv.org/abs/2610.00001v1</id><published>2026-10-15T17:59:59Z</published><title>T</title><summary>S</summary></entry>'
    )
    assert arxiv_catalog.to_work(entry).published == "2026-10-15"


def test_openaire_reads_publication_date():
    assert openaire_catalog.to_work({"id": "x", "mainTitle": "T", "publicationDate": "2026-12-01"}).published == "2026-12-01"


def test_pubmed_uses_the_date_the_record_reached_pubmed():
    xml = """<PubmedArticle><MedlineCitation><PMID>1</PMID><Article><ArticleTitle>T</ArticleTitle></Article></MedlineCitation>
    <PubmedData><History>
      <PubMedPubDate PubStatus="received"><Year>2026</Year><Month>1</Month><Day>2</Day></PubMedPubDate>
      <PubMedPubDate PubStatus="pubmed"><Year>2026</Year><Month>10</Month><Day>6</Day></PubMedPubDate>
    </History></PubmedData></PubmedArticle>"""
    assert pubmed_catalog.to_work(ElementTree.fromstring(xml)).published == "2026-10-06"
    sem = "<PubmedArticle><MedlineCitation><PMID>2</PMID></MedlineCitation></PubmedArticle>"
    assert pubmed_catalog.to_work(ElementTree.fromstring(sem)).published == ""
    ruim = ("<PubmedArticle><MedlineCitation><PMID>3</PMID></MedlineCitation><PubmedData><History>"
            '<PubMedPubDate PubStatus="pubmed"><Year>2026</Year><Month>Oct</Month><Day>6</Day></PubMedPubDate></History></PubmedData></PubmedArticle>')
    assert pubmed_catalog.to_work(ElementTree.fromstring(ruim)).published == ""
