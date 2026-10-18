"""Referencias para Zotero, Mendeley e EndNote (RIS, EndNote, CSL JSON, BibTeX) e os estilos IEEE, Harvard e MLA."""

import json

import pytest

import citations
from catalog import Work
from citations import Author, CitationMetadata
from exports import EXPORT_FORMATS, to_bibtex, to_csl_json, to_endnote, to_ris
from test_browse_api import env  # noqa: F401 - fixture compartilhada


def sample(ref="1", **overrides):
    base = {
        "ref": ref, "title": "Effect of <i>metformin</i> on A&B outcomes.", "authors": (Author("Silva", "Ana Maria"), Author("Souza", "Pedro")),
        "journal": "Lancet Diabetes", "year": 2024, "volume": "12", "issue": "3", "pages": "100-110", "doi": "10.1/x", "pmid": "99",
        "language": "en", "abstract": "Linha um\n  linha dois", "keywords": ("diabetes", "idosos"), "published": "2024-05-03",
    }
    base.update(overrides)
    return Work(**base)


META = CitationMetadata(
    title="Effect of metformin on outcomes.", authors=(Author("Silva", "Ana Maria"), Author("Souza", "Pedro"), Author("Lima", "Rui")),
    journal="Lancet Diabetes", year="2024", volume="12", issue="3", pages="100-110", doi="10.1/x",
)


def test_ieee_harvard_and_mla_for_three_authors():
    assert citations.format_citation(META, "IEEE") == (
        'A. M. Silva, P. Souza, and R. Lima, "Effect of metformin on outcomes," *Lancet Diabetes*, vol. 12, no. 3, pp. 100–110, 2024, doi: 10.1/x.')
    assert citations.format_citation(META, "Harvard") == (
        "Silva, A.M., Souza, P. and Lima, R. (2024) 'Effect of metformin on outcomes', *Lancet Diabetes*, 12(3), pp. 100–110. doi:10.1/x.")
    assert citations.format_citation(META, "MLA") == (
        'Silva, Ana Maria, et al. "Effect of metformin on outcomes." *Lancet Diabetes*, vol. 12, no. 3, 2024, pp. 100-110, https://doi.org/10.1/x.')


def test_styles_handle_one_two_and_no_authors_and_single_pages():
    one = CitationMetadata(title="Solo", authors=(Author("Silva", "Ana"),), journal="J", year="2020")
    two = CitationMetadata(title="Dois", authors=(Author("Silva", "Ana"), Author("Souza", "Pedro")), journal="J", year="2020", pages="e55")
    none = CitationMetadata(title="Sem autor")
    assert citations.format_citation(one, "IEEE") == 'A. Silva, "Solo," *J*, 2020.'
    assert citations.format_citation(one, "Harvard") == "Silva, A. (2020) 'Solo', *J*."
    assert citations.format_citation(one, "MLA") == 'Silva, Ana. "Solo." *J*, 2020.'
    assert citations.format_citation(two, "IEEE") == 'A. Silva and P. Souza, "Dois," *J*, p. e55, 2020.'
    assert citations.format_citation(two, "Harvard") == "Silva, A. and Souza, P. (2020) 'Dois', *J*, p. e55."
    assert citations.format_citation(two, "MLA") == 'Silva, Ana, and Pedro Souza. "Dois." *J*, 2020, p. e55.'
    assert citations.format_citation(none, "IEEE") == '"Sem autor."'
    assert citations.format_citation(none, "Harvard") == "'Sem autor' (n.d.)."
    assert citations.format_citation(none, "MLA") == '"Sem autor."'


def test_ieee_harvard_and_mla_abbreviate_long_author_lists():
    many = CitationMetadata(title="T", authors=tuple(Author(f"Autor{i}", "Nome") for i in range(8)), journal="J", year="2020")
    assert citations.format_citation(many, "IEEE").startswith("N. Autor0 et al.,")
    assert citations.format_citation(many, "Harvard").startswith("Autor0, N. et al. (2020)")
    assert citations.format_citation(many, "MLA").startswith("Autor0, Nome, et al.")


def test_endnote_refer_format():
    record = to_endnote([sample()])
    lines = record.splitlines()
    assert lines[0] == "%0 Journal Article" and "%A Silva, Ana Maria" in lines and "%A Souza, Pedro" in lines
    assert "%T Effect of metformin on A&B outcomes" in lines and "%J Lancet Diabetes" in lines and "%D 2024" in lines
    assert "%P 100-110" in lines and "%R 10.1/x" in lines and "%U https://doi.org/10.1/x" in lines and "%M PMID:99" in lines
    assert "%K diabetes" in lines and "%X Linha um linha dois" in lines  # o resumo vai em uma linha so
    assert to_endnote([sample(), sample("2")]).count("%0 Journal Article") == 2 and record.endswith("\n")


def test_csl_json_is_valid_and_typed():
    items = json.loads(to_csl_json([sample(), sample("2", authors=(), journal="", doi="", pmid="7", published="", year=2020, pages="e12")]))
    first, second = items
    assert first["type"] == "article-journal" and first["id"] != second["id"]
    assert first["author"] == [{"family": "Silva", "given": "Ana Maria"}, {"family": "Souza", "given": "Pedro"}]
    assert first["container-title"] == "Lancet Diabetes" and first["page"] == "100-110" and first["DOI"] == "10.1/x"
    assert first["issued"] == {"date-parts": [[2024, 5, 3]]} and first["abstract"] == "Linha um linha dois" and first["keyword"] == "diabetes, idosos"
    assert "author" not in second and "container-title" not in second and second["issued"] == {"date-parts": [[2020]]}
    assert second["URL"] == "https://pubmed.ncbi.nlm.nih.gov/7/"


def test_csl_date_ignores_a_publication_date_from_another_year():
    item = json.loads(to_csl_json([sample(published="2027-01-02", year=2024)]))[0]
    assert item["issued"] == {"date-parts": [[2024]]}


def test_ris_and_bibtex_carry_url_pmid_language_and_keywords():
    ris = to_ris([sample()])
    assert "JF  - Lancet Diabetes" in ris and "UR  - https://doi.org/10.1/x" in ris and "AN  - PMID:99" in ris and "LA  - en" in ris
    assert "AB  - Linha um linha dois" in ris  # sem quebra de linha dentro do campo
    bib = to_bibtex([sample()])
    assert "url = {https://doi.org/10.1/x}" in bib and "pmid = {99}" in bib and "keywords = {diabetes, idosos}" in bib
    sem_doi = to_ris([sample(doi="")])
    assert "UR  - https://pubmed.ncbi.nlm.nih.gov/99/" in sem_doi
    assert "UR  -" not in to_ris([sample(doi="", pmid="")])


@pytest.mark.parametrize("key", ["bibtex", "ris", "endnote", "csljson", "ieee", "harvard", "mla"])
def test_every_new_format_builds_for_an_empty_and_a_full_list(key):
    _, _, build = EXPORT_FORMATS[key]
    assert build([sample()]).strip()
    assert isinstance(build([]), str)


def test_single_article_endpoint_downloads_each_reference_format(env):  # noqa: F811
    for fmt, ext, marker in [("ris", "ris", "TY  - JOUR"), ("endnote", "enw", "%0 Journal Article"), ("csljson", "json", '"article-journal"'),
                             ("bibtex", "bib", "@article{"), ("apa", "txt", "(2020)")]:
        response = env.client.get("/api/discover/cite", params={"ref": "1", "format": fmt})
        assert response.status_code == 200 and marker in response.text, fmt
        assert response.headers["content-disposition"] == f'attachment; filename="referencia.{ext}"'
        assert response.headers["cache-control"] == "no-store"


def test_single_article_endpoint_rejects_bad_formats_and_missing_articles(env):  # noqa: F811
    assert env.client.get("/api/discover/cite", params={"ref": "1", "format": "csv"}).status_code == 400
    assert env.client.get("/api/discover/cite", params={"ref": "1", "format": "docx"}).status_code == 400
    assert env.client.get("/api/discover/cite", params={"ref": "nao-existe", "format": "ris"}).status_code == 404
    assert env.client.get("/api/discover/cite", params={"format": "ris"}).status_code == 422


def test_library_export_offers_the_new_formats(env):  # noqa: F811
    client = env.login(env.build())
    client.post("/api/library", json={"ref": "1"})
    for fmt in ("endnote", "csljson", "ieee", "harvard", "mla"):
        response = client.get("/api/library/export", params={"format": fmt})
        assert response.status_code == 200 and response.text.strip(), fmt
    assert json.loads(client.get("/api/library/export", params={"format": "csljson"}).text)[0]["type"] == "article-journal"
