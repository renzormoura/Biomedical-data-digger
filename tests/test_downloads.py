"""Documentos para baixar: renderizacao, DOCX valido, texto completo JATS, planilha segura e rotas."""

import io
import zipfile
from unittest.mock import MagicMock, patch
from xml.etree.ElementTree import fromstring

import pytest
import requests
from fastapi.testclient import TestClient

import downloads
from catalog import CatalogError, Work
from citations import Author
from config import Settings
from db import Database
from discovery import DiscoveryService
from exports import EXPORT_FORMATS, to_abstracts, to_csv, to_json
from library_store import LibraryStore
from ratelimit import SlidingWindowLimiter
from web import create_app
from workflow import AnalysisService, ArticleRepository

ABSTRACT = (
    "Background: Metformin is widely used. Methods: We pooled 14 trials (n=18,450). "
    "Results: Lower risk (RR 0.89; 95% CI 0.81-0.98; p=0.02). Conclusions: A modest reduction."
)


def make_work(**overrides):
    base = {
        "ref": "1", "title": 'Estudo <script>alert(1)</script> & "aspas"', "authors": (Author("Weber", "Anika"), Author("Suzuki", "Hiro")),
        "journal": "Revista Exemplo", "year": 2023, "volume": "41", "issue": "2", "pages": "112-124", "doi": "10.0000/exemplo.001",
        "pmid": "1", "pmcid": "PMC7281364", "abstract": ABSTRACT, "study_types": ("Meta-análise",), "source": "Europe PMC", "open_access": True,
        "oa_url": "https://example.org/aberto.pdf",
    }
    base.update(overrides)
    return Work(**base)


SECTIONS = [("Contexto", "Metformin is widely used."), ("Resultados", "Lower risk (RR 0.89).")]

JATS = b"""<?xml version="1.0"?>
<!DOCTYPE article PUBLIC "-//NLM//DTD JATS (Z39.96) Journal Archiving and Interchange DTD v1.2 20190208//EN" "JATS-archivearticle1.dtd">
<article><front><article-meta><permissions><license><license-p>CC BY 4.0 <ext-link>x</ext-link></license-p></license></permissions></article-meta></front>
<body>
<sec><title>1. Introduction</title><p>Primeiro   paragrafo com <italic>it&#225;lico</italic> e <xref>[1]</xref>.</p>
  <sec><title>1.1 Contexto</title><p>Sub paragrafo.</p></sec></sec>
<sec><title>2. Methods</title><p>Metodos.</p><fig><label>Figure 1</label><caption><p>Fluxo do estudo.</p></caption></fig></sec>
</body><back><ref-list><ref><label>1.</label><mixed-citation>Autor A. Titulo. Revista. 2020.</mixed-citation></ref></ref-list></back></article>"""


# ------------------------------------------------------------------ renderizacao
def test_html_escapes_everything_and_has_no_active_content():
    html = downloads.to_html(downloads.abstract_blocks(make_work(), SECTIONS)).lower()
    assert "<script" not in html and "&lt;script&gt;" in html and "&amp;" in html
    assert "<link" not in html and "http-equiv" not in html and "<style>" in html and 'lang="pt-br"' in html


def test_txt_and_markdown_have_title_sections_and_identity():
    blocks = downloads.abstract_blocks(make_work(), SECTIONS)
    txt, md = downloads.to_txt(blocks), downloads.to_md(blocks)
    assert "https://doi.org/10.0000/exemplo.001" in txt and "Contexto" in txt and "RESUMO" in txt
    assert md.startswith("# Estudo") and "## Resumo" in md and "### Contexto" in md and "PMID: 1" in md
    assert "gerado por IA" in md.lower() or "nada foi gerado por IA" in md


def test_docx_is_a_valid_package_with_escaped_text_and_no_invalid_xml_chars():
    blocks = downloads.abstract_blocks(make_work(title="Título com \x00 controle & <tag>"), SECTIONS)
    data = downloads.to_docx(blocks)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert set(archive.namelist()) == {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
        document = archive.read("word/document.xml").decode("utf-8")
        for name in archive.namelist():
            fromstring(archive.read(name))  # todo XML precisa ser bem formado
    assert "\x00" not in document and "&amp; &lt;tag&gt;" in document and "Metformin" in document


def test_render_returns_bytes_and_media_types():
    blocks = [("title", "T"), ("p", "texto")]
    for fmt, media in (("txt", "text/plain"), ("md", "text/markdown"), ("html", "text/html")):
        content, mime = downloads.render(blocks, fmt)
        assert isinstance(content, bytes) and mime.startswith(media) and "charset=utf-8" in mime
    content, mime = downloads.render(blocks, "docx")
    assert content[:2] == b"PK" and "wordprocessingml" in mime


def test_sheet_contains_numbers_reliability_registry_and_citations():
    reliability = {"score": 78, "band": "Alta", "coverage": 100, "disclaimer": "Não avalia a execução.",
                   "criteria": [{"name": "Desenho", "status": "met", "points": 22.5, "weight": 25, "detail": "RCT", "evidence": "Ensaio"}]}
    extra = {"trials": [{"nct": "NCT04280705", "status": "Concluído", "title": "ACTT", "url": "https://clinicaltrials.gov/study/NCT04280705"}],
             "citations": 1806, "relatedData": [{"kind": "Dataset", "title": "Dados", "url": "https://doi.org/10.5281/zenodo.1"}]}
    blocks = downloads.sheet_blocks(make_work(), SECTIONS, [("valor de p", "p=0.02")], reliability, {"ABNT": "SILVA, A."}, extra)
    text = downloads.to_txt(blocks)
    for expected in ("p=0.02", "78/100 (Alta)", "Desenho (met, 22.5/25)", "Evidência: Ensaio", "NCT04280705", "1806", "Dados", "ABNT: SILVA, A.", "Ficha de leitura"):
        assert expected in text


def test_safe_filename_is_ascii_and_bounded():
    name = downloads.safe_filename(make_work(title="Ação/Reação: ../../etc/passwd \"x\" " + "a" * 200), "resumo", "txt")
    assert name.endswith("-2023-resumo.txt") and len(name) < 90 and "/" not in name and ".." not in name.replace("-resumo.txt", "")
    assert downloads.safe_filename(make_work(title="???", year=None), "ficha", "md") == "artigo-ficha.md"


# ------------------------------------------------------------------ texto completo (JATS)
def test_jats_is_converted_into_sections_captions_and_references():
    fulltext = downloads.jats_to_fulltext("PMC1", JATS)
    kinds = [(k, t) for k, t in fulltext.blocks]
    assert ("h2", "1. Introduction") in kinds and ("h3", "1.1 Contexto") in kinds
    assert ("p", "Primeiro paragrafo com itálico e [1].") in kinds
    assert ("quote", "Figure 1: Fluxo do estudo.") in kinds and ("h1", "Referências") in kinds
    assert ("li", "1. Autor A. Titulo. Revista. 2020.") in kinds and "CC BY 4.0" in fulltext.license
    assert fulltext.xml == JATS
    document = downloads.to_md(downloads.fulltext_blocks(make_work(), fulltext))
    assert "Licença: CC BY 4.0" in document and "## Texto completo" in document


def test_jats_without_body_or_with_entities_is_refused():
    with pytest.raises(CatalogError, match="texto completo"):
        downloads.jats_to_fulltext("PMC1", b"<article><front/><body/></article>")
    with pytest.raises(CatalogError):
        downloads.jats_to_fulltext("PMC1", b'<!DOCTYPE a [<!ENTITY x "y">]><article><body><p>&x;</p></body></article>')


def test_fetch_fulltext_validates_pmcid_status_size_and_network_errors():
    ok = MagicMock(status_code=200, content=JATS)
    with patch.object(downloads.requests, "get", return_value=ok) as get:
        assert downloads.fetch_fulltext_xml("PMC7281364") == JATS and "PMC7281364/fullTextXML" in get.call_args.args[0]
        assert downloads.fetch_fulltext_xml("PMC1; rm") is None and get.call_count == 1
    with patch.object(downloads.requests, "get", return_value=MagicMock(status_code=404, content=b"")):
        assert downloads.fetch_fulltext_xml("PMC1") is None
    with patch.object(downloads.requests, "get", return_value=MagicMock(status_code=200, content=b"x" * (downloads.MAX_FULLTEXT_BYTES + 1))), \
            pytest.raises(CatalogError, match="grande demais"):
        downloads.fetch_fulltext_xml("PMC1")
    with patch.object(downloads.requests, "get", side_effect=requests.Timeout("x")), pytest.raises(CatalogError):
        downloads.fetch_fulltext_xml("PMC1")


def test_menu_lists_kinds_formats_and_only_open_links():
    unavailable = downloads.menu(make_work(oa_url="javascript:alert(1)", pmcid=""), None, "Sem texto.")
    options = {o["kind"]: o for o in unavailable["options"]}
    assert list(options) == ["abstract", "sheet", "citation", "fulltext"] and options["fulltext"]["available"] is False
    assert options["fulltext"]["description"] == "Sem texto." and [f["id"] for f in options["citation"]["formats"]][0] == "bibtex"
    assert [link["url"] for link in unavailable["links"]] == ["https://doi.org/10.0000/exemplo.001"]  # esquema perigoso descartado
    available = downloads.menu(make_work(), downloads.jats_to_fulltext("PMC7281364", JATS))
    assert {o["kind"]: o["available"] for o in available["options"]}["fulltext"] is True
    assert "https://europepmc.org/articles/PMC7281364?pdf=render" in [link["url"] for link in available["links"]]


# ------------------------------------------------------------------ exportacao em lote
def test_csv_neutralises_formulas_and_keeps_accents_for_excel():
    works = [make_work(title="=HYPERLINK(\"http://x\")", abstract="linha1\nlinha2"), make_work(ref="2", title="Normal ação")]
    out = to_csv(works)
    assert out.startswith("﻿") and "'=HYPERLINK" in out and "linha1 linha2" in out and "Normal ação" in out
    assert out.splitlines()[0].startswith("﻿titulo,autores,periodico")


def test_json_and_abstracts_exports():
    assert '"title"' in to_json([make_work()]) and "ação" not in to_json([make_work(title="ação")]).encode("ascii", "ignore").decode()
    md = to_abstracts([make_work(), make_work(ref="2", abstract="")])
    assert md.startswith("# Resumos") and "Metformin is widely used" in md and "Sem resumo no registro." in md
    assert {"csv", "json", "resumos"} <= set(EXPORT_FORMATS)


# ------------------------------------------------------------------ rotas
class Catalog:
    id, name = "europepmc", "Europe PMC (x)"

    def __init__(self, works):
        self._works = {w.ref: w for w in works}

    def study_types(self):
        return ()

    def search(self, query):
        raise AssertionError("nao deve buscar")

    def get(self, ref):
        return self._works.get(ref)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "a.sqlite3"))
    library = LibraryStore(Database(database_url="", sqlite_path=str(tmp_path / "a.sqlite3")))
    library.initialize()
    catalog = Catalog([make_work(), make_work(ref="2", title="Sem texto completo", pmcid="", oa_url="")])
    discovery = DiscoveryService([catalog], SlidingWindowLimiter(100, 60), fallback=None)
    repository = ArticleRepository(lambda raw: ("T", "Resumo suficiente para o teste.", "s"))
    service = AnalysisService(repository, MagicMock(), SlidingWindowLimiter(50, 60))
    app = create_app(service, repository, Settings(session_secret="k" * 40), search_fn=lambda *a, **k: [], discovery=discovery, library=library)
    return TestClient(app, base_url="http://testserver")


def get(client, kind, fmt, ref="1"):
    return client.get("/api/discover/download", params={"ref": ref, "kind": kind, "format": fmt})


def test_abstract_and_sheet_downloads_in_every_format(client):
    for kind in ("abstract", "sheet"):
        for fmt in downloads.KIND_FORMATS[kind]:
            response = get(client, kind, fmt)
            assert response.status_code == 200, (kind, fmt)
            assert response.headers["content-disposition"].startswith('attachment; filename="estudo-')
            assert response.headers["x-content-type-options"] == "nosniff" and response.headers["cache-control"] == "no-store"
    assert "Metformin" in get(client, "abstract", "txt").text and "Confiabilidade" in get(client, "sheet", "md").text
    assert get(client, "sheet", "json").json()["reliability"]["criteria"]
    assert get(client, "abstract", "docx").content[:2] == b"PK"
    assert "<script>" not in get(client, "sheet", "html").text.lower().replace("&lt;script&gt;", "")


def test_citation_downloads_use_the_export_builders(client):
    bib = get(client, "citation", "bibtex")
    assert bib.status_code == 200 and "@article{" in bib.text and bib.headers["content-disposition"].endswith('.bib"')
    assert get(client, "citation", "ris").text.startswith("TY  - JOUR") and "WEBER" in get(client, "citation", "abnt").text.upper()


def test_download_validates_kind_and_format(client):
    assert get(client, "abstract", "pdf").status_code == 400 and get(client, "nada", "txt").status_code == 400
    assert get(client, "citation", "txt").status_code == 400 and get(client, "fulltext", "bibtex").status_code == 400
    assert client.get("/api/discover/download", params={"ref": "", "kind": "abstract"}).status_code == 422
    assert get(client, "abstract", "txt", ref="999").status_code == 404


def test_fulltext_download_uses_europe_pmc_when_open_and_404_when_not(client):
    with patch.object(downloads, "fetch_fulltext_xml", return_value=JATS) as fetch:
        txt = get(client, "fulltext", "txt")
        assert txt.status_code == 200 and "Primeiro paragrafo" in txt.text and "Introduction" in txt.text
        assert get(client, "fulltext", "xml").content == JATS and get(client, "fulltext", "docx").content[:2] == b"PK"
        assert fetch.call_count == 1  # resultado em cache
    with patch.object(downloads, "fetch_fulltext_xml", return_value=None):
        assert get(client, "fulltext", "txt", ref="2").status_code == 404
    with patch.object(downloads, "fetch_fulltext_xml", side_effect=CatalogError("fora do ar")):
        assert get(client, "fulltext", "txt", ref="2").status_code in {404, 503}


def test_downloads_menu_endpoint_reports_availability_and_survives_source_failures(client):
    with patch.object(downloads, "fetch_fulltext_xml", return_value=JATS):
        menu = client.get("/api/discover/downloads", params={"ref": "1"}).json()
    assert {o["kind"]: o["available"] for o in menu["options"]} == {"abstract": True, "sheet": True, "citation": True, "fulltext": True}
    assert any(link["label"].startswith("PDF") for link in menu["links"])
    with patch.object(downloads, "fetch_fulltext_xml", side_effect=CatalogError("fora do ar")):
        degraded = client.get("/api/discover/downloads", params={"ref": "2"}).json()
    full = next(o for o in degraded["options"] if o["kind"] == "fulltext")
    assert full["available"] is False and full["description"]


def test_library_batch_exports_include_csv_json_and_abstracts(client):
    client.post("/api/auth/register", json={"email": "ana@exemplo.com", "password": "senha-de-teste-local-9"})
    assert client.post("/api/library", json={"ref": "1"}).status_code == 200
    csv_response = client.get("/api/library/export", params={"format": "csv"})
    assert csv_response.status_code == 200 and csv_response.headers["content-disposition"].endswith('biblioteca.csv"')
    assert csv_response.content.startswith(b"\xef\xbb\xbf")
    assert client.get("/api/library/export", params={"format": "json"}).json()[0]["doi"] == "10.0000/exemplo.001"
    assert "Metformin" in client.get("/api/library/export", params={"format": "resumos"}).text
