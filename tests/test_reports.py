"""Relatorio de tema: armazenamento, calculo (panorama, metodo, blocos) e rotas com download em HTML e DOCX."""

import io
import zipfile
from datetime import date
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import reports
from account_store import AccountStore
from catalog import Work
from citations import Author
from config import Settings
from db import Database
from discovery import DiscoveryService
from domain import LimitReachedError, NotFoundError
from library_store import LibraryStore
from ratelimit import SlidingWindowLimiter
from reports import ReportStore, assess_study, method_paragraphs, panorama, report_blocks
from web import create_app
from workflow import AnalysisService, ArticleRepository

EMAIL = "ana@exemplo.com"
ABSTRACT = (
    "Background: Hypertension is common. Methods: We randomized 240 patients to exercise or control. "
    "Results: Systolic pressure fell by 8.2 mmHg (95% CI 5.1 to 11.3; p < 0.001). Conclusions: Exercise helps."
)


def make_work(ref, title=None, **overrides):
    base = {
        "ref": ref, "title": title or f"Estudo {ref} sobre exercício", "authors": (Author("Silva", "Ana"),), "journal": "Revista X",
        "year": 2023, "doi": f"10.1/{ref}", "abstract": ABSTRACT, "study_types": ("Ensaio clínico randomizado",),
        "language": "pt", "source": "Europe PMC", "open_access": True,
    }
    base.update(overrides)
    return Work(**base)


@pytest.fixture
def store(tmp_path):
    result = ReportStore(Database(database_url="", sqlite_path=str(tmp_path / "r.sqlite3")))
    result.initialize()
    return result


def create(store, works=None, **kwargs):
    return store.create(EMAIL, list_name="Hipertensão", works=works or [make_work("1"), make_work("2"), make_work("3", year=2021, language="en")], **kwargs)


# ------------------------------------------------------------------ armazenamento
def test_create_freezes_the_studies_and_defaults_the_title(store):
    report = create(store)
    assert report.title == "Relatório: Hipertensão" and report.version == 1 and report.question == ""
    assert [i.work.ref for i in report.items] == ["1", "2", "3"] and all(i.included and not i.note for i in report.items)
    assert report.items[0].work.abstract == ABSTRACT  # o retrato guarda o resumo para calcular sem rede


def test_create_validates_and_limits(store):
    with pytest.raises(NotFoundError):
        store.create(EMAIL, list_name="Vazia", works=[])
    for index in range(reports.MAX_REPORTS):
        store.create(EMAIL, list_name="L", works=[make_work(str(index))])
    with pytest.raises(LimitReachedError):
        store.create(EMAIL, list_name="L", works=[make_work("x")])
    assert store.create("outra@exemplo.com", list_name="L", works=[make_work("1")]).version == 1  # o limite e por conta


def test_update_changes_inclusion_notes_and_bumps_the_version(store):
    report = create(store)
    updated = store.update(EMAIL, report.id, title="  Meu referencial ", question="Exercício reduz a pressão?\n\nEm adultos.",
                           method_note="Busquei só em português.", items=[("1", False, "Fora do escopo"), ("2", True, "Principal"), ("zzz", True, "ignorado")])
    assert updated.title == "Meu referencial" and updated.version == 2 and updated.question.startswith("Exercício")
    assert [(i.work.ref, i.included, i.note) for i in updated.items] == [("1", False, "Fora do escopo"), ("2", True, "Principal"), ("3", True, "")]
    assert len(updated.included) == 2 and updated.method_note == "Busquei só em português."
    assert store.update(EMAIL, report.id, title="", question="", method_note="", items=[]).title == "Meu referencial"  # titulo vazio mantem


def test_text_is_cleaned_and_truncated(store):
    report = create(store, title="T\x00itulo\x07", question="q" * (reports.MAX_QUESTION_CHARS + 50))
    assert "\x00" not in report.title and len(report.question) == reports.MAX_QUESTION_CHARS
    updated = store.update(EMAIL, report.id, title="x" * 500, question="", method_note="m" * 5000, items=[("1", True, "n" * 3000)])
    assert len(updated.title) == reports.MAX_TITLE_CHARS and len(updated.method_note) == reports.MAX_METHOD_NOTE_CHARS
    assert len(updated.items[0].note) == reports.MAX_ITEM_NOTE_CHARS


def test_summaries_isolation_and_delete(store):
    first = create(store)
    other = store.create("outra@exemplo.com", list_name="Outra", works=[make_work("9")])
    store.update(EMAIL, first.id, title="", question="", method_note="", items=[("1", False, "")])
    [summary] = store.summaries(EMAIL)
    assert (summary.id, summary.included, summary.total, summary.version) == (first.id, 2, 3, 2)
    with pytest.raises(NotFoundError):
        store.get(EMAIL, other.id)
    with pytest.raises(NotFoundError):
        store.update(EMAIL, other.id, title="x", question="", method_note="", items=[])
    with pytest.raises(NotFoundError):
        store.delete(EMAIL, other.id)
    store.delete(EMAIL, first.id)
    assert store.summaries(EMAIL) == [] and store.get("outra@exemplo.com", other.id).title.startswith("Relatório")


def test_corrupt_snapshot_degrades_gracefully(store):
    report = create(store)
    store._db.execute("UPDATE report_items SET data = 'quebrado' WHERE ref = '1'")  # noqa: SLF001
    assert store.get(EMAIL, report.id).items[0].work.title == "Título não informado"


# ------------------------------------------------------------------ calculo
def test_panorama_counts_types_years_languages_and_flags():
    works = [make_work("1"), make_work("2", study_types=()), make_work("3", year=2021, language="en", open_access=False, abstract="", retracted=True),
             make_work("4", language="", source="")]
    data = panorama(works)
    assert data["total"] == 4 and data["openAccess"] == 3 and data["retracted"] == 1 and data["withoutAbstract"] == 1
    assert ("Ensaio clínico randomizado", 3) in data["types"] and (reports.NO_TYPE, 1) in data["types"]
    assert data["years"] == [("2023", 3), ("2021", 1)]
    assert ("pt", 2) in data["languages"] and (reports.NO_LANGUAGE, 1) in data["languages"] and ("Fonte não informada", 1) in data["sources"]
    assert panorama([])["total"] == 0


def test_assess_study_uses_only_the_stored_record():
    result = assess_study(make_work("1"))
    assert result.reliability.score is not None and result.findings
    assert any("95%" in f.sentence or "p < 0.001" in f.sentence for f in result.findings)
    sem_resumo = assess_study(make_work("2", abstract=""))
    assert sem_resumo.findings == () and any("Sem resumo" in w for w in sem_resumo.reliability.warnings)


def test_method_paragraphs_state_counts_sources_and_limits(store):
    report = store.update(EMAIL, create(store).id, title="", question="", method_note="", items=[("3", False, "")])
    text = "\n".join(method_paragraphs(report, date(2026, 10, 18)))
    assert "lista de leitura “Hipertensão”" in text and "Foram reunidos 3 estudos; 2 foram incluídos e 1 excluídos" in text
    assert "Europe PMC (3)" in text and "não são registradas" in text and "não substitui a leitura crítica" in text
    assert "versão 2" in text and "18/10/2026" in text and "Nenhum texto deste relatório foi gerado por IA" in text
    assert EMAIL not in text


def test_report_blocks_has_every_section_in_order(store):
    report = create(store, title="Exercício e pressão", question="Exercício reduz a pressão arterial?")
    report = store.update(EMAIL, report.id, title="", question="Exercício reduz a pressão arterial?", method_note="Busca feita em outubro.\nSó em português.",
                          items=[("1", True, "Estudo central"), ("3", False, "Em inglês")])
    blocks = report_blocks(report, date(2026, 10, 18))
    headings = [text for kind, text in blocks if kind in ("title", "h1")]
    assert headings == ["Exercício e pressão", "Pergunta ou tema", "Panorama dos estudos incluídos", "Estudos incluídos", "Referências", "Apêndice: método"]
    flat = "\n".join(text for _, text in blocks)
    assert "1. Estudo 1 sobre exercício" in flat and "2. Estudo 2 sobre exercício" in flat and "Estudo 3 sobre exercício" in flat  # o 3 so aparece como excluido
    assert "3. Estudo 3" not in flat and "Nota do autor: Estudo central" in flat
    assert "Estudos reunidos e excluídos pelo autor" in flat and "Em inglês" in flat and "Busca feita em outubro." in flat
    assert any(kind == "quote" and "mmHg" in text for kind, text in blocks)
    assert "Confiabilidade: " in flat and "/100" in flat
    for style in reports.REFERENCE_STYLES:
        assert ("h2", style) in blocks
    assert EMAIL not in flat


def test_report_blocks_handles_no_included_studies(store):
    report = store.update(EMAIL, create(store).id, title="", question="", method_note="", items=[(r, False, "") for r in ("1", "2", "3")])
    flat = "\n".join(text for _, text in report_blocks(report))
    assert "Nenhum estudo foi incluído." in flat and "Sem estudos incluídos." in flat


# ------------------------------------------------------------------ rotas
class Catalog:
    id, name = "fake", "Fake"

    def study_types(self):
        return ()

    def search(self, query):
        raise AssertionError("nao deve buscar")

    def get(self, ref):
        return make_work(ref)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "app.sqlite3"))
    AccountStore().initialize()
    database = Database(database_url="", sqlite_path=str(tmp_path / "app.sqlite3"))
    library = LibraryStore(database)
    library.initialize()
    report_store = ReportStore(database)
    report_store.initialize()
    discovery = DiscoveryService([Catalog()], SlidingWindowLimiter(100, 60), fallback=None)
    repository = ArticleRepository(lambda raw: ("T", "Resumo suficiente para o teste.", "s"))
    service = AnalysisService(repository, MagicMock(), SlidingWindowLimiter(50, 60))
    settings = Settings(session_secret="k" * 40, login_attempts_per_minute=100)

    def client(email=EMAIL):
        app = create_app(service, repository, settings, account_store_factory=lambda: AccountStore(), search_fn=lambda *a, **k: [],
                         discovery=discovery, library=library, reports=report_store)
        test_client = TestClient(app, base_url="http://testserver")
        if email:
            assert test_client.post("/api/auth/register", json={"email": email, "password": "senha-forte-123"}).status_code == 200
        return test_client

    return type("Env", (), {"client": staticmethod(client), "library": library})


def seeded(env, client):
    created = env.library.create_list(EMAIL, "Hipertensão")
    for work in (make_work("1"), make_work("2")):
        env.library.add_to_list(EMAIL, created.id, work)
    return created.id


def test_routes_require_login(env):
    anonimo = env.client(None)
    for method, url in [("get", "/api/reports"), ("get", "/api/reports/x"), ("delete", "/api/reports/x"), ("get", "/api/reports/x/download")]:
        assert getattr(anonimo, method)(url).status_code == 401
    assert anonimo.post("/api/reports", json={"list_id": "x"}).status_code == 401
    assert anonimo.put("/api/reports/x", json={}).status_code == 401


def test_create_edit_and_read_a_report_through_the_api(env):
    client = env.client()
    list_id = seeded(env, client)
    created = client.post("/api/reports", json={"list_id": list_id, "title": "Exercício e pressão", "question": "Funciona?"}).json()
    assert created["title"] == "Exercício e pressão" and created["version"] == 1 and len(created["items"]) == 2
    first = created["items"][0]
    assert first["included"] and first["reliability"]["score"] is not None and first["findings"] and first["work"]["title"].startswith("Estudo 1")
    assert created["panorama"]["total"] == 2 and created["method"] and created["criteria"]
    saved = client.put(f"/api/reports/{created['id']}", json={
        "title": "Novo título", "question": "Funciona?", "methodNote": "Nota livre", "items": [{"ref": "1", "included": False, "note": "fora"}],
    }).json()
    assert saved["version"] == 2 and saved["methodNote"] == "Nota livre" and saved["panorama"]["total"] == 1
    assert [i["included"] for i in saved["items"]] == [False, True] and saved["items"][0]["note"] == "fora"
    assert client.get(f"/api/reports/{created['id']}").json()["title"] == "Novo título"
    [summary] = client.get("/api/reports").json()["reports"]
    assert summary["included"] == 1 and summary["total"] == 2 and summary["listName"] == "Hipertensão"
    assert client.delete(f"/api/reports/{created['id']}").json() == {"ok": True}
    assert client.get(f"/api/reports/{created['id']}").status_code == 404


def test_create_from_missing_or_empty_list_and_foreign_reports(env):
    client = env.client()
    assert client.post("/api/reports", json={"list_id": "nao-existe"}).status_code == 404
    empty = env.library.create_list(EMAIL, "Vazia")
    assert client.post("/api/reports", json={"list_id": empty.id}).status_code == 404
    created = client.post("/api/reports", json={"list_id": seeded(env, client)}).json()
    outra = env.client("bia@exemplo.com")
    assert outra.get(f"/api/reports/{created['id']}").status_code == 404
    assert outra.delete(f"/api/reports/{created['id']}").status_code == 404
    assert outra.get(f"/api/reports/{created['id']}/download").status_code == 404
    assert outra.get("/api/reports").json() == {"reports": []}


def test_download_html_docx_markdown_and_text(env):
    client = env.client()
    created = client.post("/api/reports", json={"list_id": seeded(env, client), "title": "Exercício e pressão"}).json()
    base = f"/api/reports/{created['id']}/download"
    html = client.get(base, params={"format": "html"})
    assert html.status_code == 200 and "<h1>Exercício e pressão</h1>" in html.text and "Apêndice: método" in html.text
    assert html.headers["content-disposition"].startswith('attachment; filename="relatorio-exercicio-e-pressao') and html.headers["cache-control"] == "no-store"
    assert client.get(base).headers["content-type"].startswith("text/html")  # padrao: html
    docx = client.get(base, params={"format": "docx"})
    assert docx.status_code == 200 and docx.headers["content-disposition"].endswith('.docx"')
    with zipfile.ZipFile(io.BytesIO(docx.content)) as archive:
        assert "Exercício e pressão" in archive.read("word/document.xml").decode("utf-8")
    assert "## Referências" in client.get(base, params={"format": "md"}).text
    assert "APÊNDICE: MÉTODO" in client.get(base, params={"format": "txt"}).text
    assert client.get(base, params={"format": "pdf"}).status_code == 400


def test_html_escapes_user_text(env):
    client = env.client()
    created = client.post("/api/reports", json={"list_id": seeded(env, client), "title": "<script>alert(1)</script>"}).json()
    page = client.get(f"/api/reports/{created['id']}/download", params={"format": "html"}).text
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page


# ------------------------------------------------------------------ situacao no Brasil (pacote de saude)
from unittest.mock import patch  # noqa: E402

import report_brasil  # noqa: E402
from brasil import anvisa, conitec, rename  # noqa: E402

DRUGS = "Metformin and aspirin were compared with placebo; dapagliflozin was an add-on."


def drug_work(ref, **overrides):
    return make_work(ref, title=f"Estudo {ref} de medicamentos", abstract=DRUGS, **overrides)


@pytest.fixture(scope="module")
def bases():
    return anvisa.carregar(), conitec.carregar(), rename.carregar()


def test_clean_substances_normalizes_dedupes_and_limits():
    cleaned = reports.clean_substances(["Ácido Acetilsalicílico", "acido acetilsalicilico", "ab", "  Metformina ", ""] + [f"droga{i}" for i in range(20)])
    assert cleaned[:2] == ["acido acetilsalicilico", "metformina"] and len(cleaned) == reports.MAX_SUBSTANCES and "ab" not in cleaned


def test_substances_are_saved_kept_cleared_and_isolated(store):
    report = create(store)
    assert report.substances == ()
    saved = store.update(EMAIL, report.id, title="", question="", method_note="", items=[], substances=["Metformina", "Aspirina"])
    assert saved.substances == ("metformina", "aspirina")
    assert store.update(EMAIL, report.id, title="", question="", method_note="", items=[]).substances == ("metformina", "aspirina")  # None mantem
    assert store.update(EMAIL, report.id, title="", question="", method_note="", items=[], substances=["Insulina"]).substances == ("insulina",)
    assert store.update(EMAIL, report.id, title="", question="", method_note="", items=[], substances=[]).substances == ()
    store.update(EMAIL, report.id, title="", question="", method_note="", items=[], substances=["x" * 200])
    assert len(store.get(EMAIL, report.id).substances[0]) == reports.MAX_SUBSTANCE_CHARS
    store.delete(EMAIL, report.id)
    assert store._db.query("SELECT COUNT(*) FROM report_substances")[0][0] == 0  # noqa: SLF001


def test_suggest_ranks_by_how_many_studies_cite_the_substance(bases):
    works = [drug_work("1"), drug_work("2"), make_work("3", abstract="Metformin alone in obese adults.", title="Outro")]
    suggestions = {s.termo: s for s in report_brasil.suggest(works, bases)}
    assert suggestions["metformina"].studies == 3 and suggestions["dapagliflozina"].studies == 2
    ordered = [s.termo for s in report_brasil.suggest(works, bases)]
    assert ordered.index("metformina") < ordered.index("dapagliflozina")
    assert suggestions["metformina"].nome == "Metformina" and suggestions["metformina"].en == "metformin" and suggestions["metformina"].metodo
    assert report_brasil.suggest([make_work("9", abstract="Exercise and blood pressure in adults.")], bases) == []
    assert report_brasil.suggest([], bases) == []


def test_build_describes_rename_anvisa_and_conitec_with_dates(bases):
    section = report_brasil.build(("metformina", "dapagliflozina", "substanciainexistente"), bases)
    flat = "\n".join(text for _, text in section.blocks)
    assert ("h1", "Situação no Brasil") in section.blocks and ("h2", "Metformina") in section.blocks
    assert "Rename 2024" in flat and "consta, componente básico" in flat and "registros ativos" in flat
    assert "Conitec:" in flat and "decisões registradas" in flat  # dapagliflozina tem decisoes
    assert "nenhum registro de medicamento" in flat and "não consta na relação nacional" in flat  # substancia inexistente
    assert "extraído em" in flat and "não significa disponibilidade" in flat and "ainda não foram revisados por farmacêutico ou médico" in flat
    assert "confirmou as substâncias" in section.method and "extraído em" in section.method
    assert report_brasil.build((), bases) is None


def test_report_blocks_places_the_brazil_section_between_studies_and_references(store, bases):
    report = store.update(EMAIL, create(store).id, title="", question="", method_note="", items=[], substances=["metformina"])
    section = report_brasil.build(report.substances, bases)
    blocks = report_blocks(report, date(2026, 10, 18), brasil=section)
    headings = [text for kind, text in blocks if kind == "h1"]
    assert headings.index("Estudos incluídos") < headings.index("Situação no Brasil") < headings.index("Referências")
    assert section.method in [text for _, text in blocks]
    assert "Situação no Brasil" not in [text for _, text in report_blocks(report, date(2026, 10, 18))]


def seeded_drugs(env):
    created = env.library.create_list(EMAIL, "Metformina")
    for work in (drug_work("1"), drug_work("2")):
        env.library.add_to_list(EMAIL, created.id, work)
    return created.id


def test_brasil_routes_suggest_confirm_and_describe(env):
    client = env.client()
    report = client.post("/api/reports", json={"list_id": seeded_drugs(env)}).json()
    first = client.get(f"/api/reports/{report['id']}/brasil").json()
    assert {"metformina", "dapagliflozina"} <= {s["termo"] for s in first["suggestions"]} and first["confirmed"] == []
    assert set(first["meta"]) == {"anvisa", "conitec", "rename"}
    saved = client.put(f"/api/reports/{report['id']}", json={"title": "", "items": [], "substances": ["Metformina", "dapagliflozina"]}).json()
    assert saved["substances"] == ["metformina", "dapagliflozina"]
    again = client.get(f"/api/reports/{report['id']}/brasil").json()
    names = {c["termo"]: c for c in again["confirmed"]}
    assert names["metformina"]["nome"] == "Metformina" and names["metformina"]["rename"] and names["metformina"]["anvisa"]
    assert names["dapagliflozina"]["conitec"]
    kept = client.put(f"/api/reports/{report['id']}", json={"title": "", "items": []}).json()
    assert kept["substances"] == ["metformina", "dapagliflozina"]  # sem o campo, nao apaga


def test_download_includes_the_brazil_section_only_for_confirmed_substances(env):
    client = env.client()
    report = client.post("/api/reports", json={"list_id": seeded_drugs(env), "title": "Metformina no diabetes"}).json()
    url = f"/api/reports/{report['id']}/download"
    assert "Situação no Brasil" not in client.get(url).text
    client.put(f"/api/reports/{report['id']}", json={"title": "", "items": [], "substances": ["metformina"]})
    page = client.get(url).text
    assert "Situação no Brasil" in page and "Rename 2024" in page and "ANVISA" in page and "confirmou as substâncias" in page
    assert "Situação no Brasil" in client.get(url, params={"format": "md"}).text


def test_brasil_routes_degrade_without_snapshots_and_require_login(env):
    client = env.client()
    report = client.post("/api/reports", json={"list_id": seeded_drugs(env)}).json()
    client.put(f"/api/reports/{report['id']}", json={"title": "", "items": [], "substances": ["metformina"]})
    with patch.object(rename, "carregar", side_effect=FileNotFoundError("sem arquivo")):
        assert client.get(f"/api/reports/{report['id']}/brasil").status_code == 503
        assert client.get(f"/api/reports/{report['id']}/download").status_code == 503  # nao entrega um documento sem a secao confirmada
    assert env.client(None).get(f"/api/reports/{report['id']}/brasil").status_code == 401
    assert env.client("bia@exemplo.com").get(f"/api/reports/{report['id']}/brasil").status_code == 404
